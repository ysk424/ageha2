"""Main-thread-only Blender Curves and evaluated Mesh input/output helpers."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import bpy
import numpy as np


@dataclass(frozen=True)
class HairSample:
    evaluated_world: np.ndarray
    original_world: np.ndarray
    modifier_offset_world: np.ndarray
    local: np.ndarray
    curve_offsets: np.ndarray


@dataclass(frozen=True)
class MeshSample:
    vertices_world: np.ndarray
    triangles: np.ndarray


@dataclass(frozen=True)
class GuideSample:
    segments_world: np.ndarray
    names: tuple[str, ...]
    armature_name: str


def curve_spans(curves_obj) -> np.ndarray:
    if curves_obj is None or curves_obj.type != "CURVES":
        raise ValueError("Hair must be a Curves object")
    spans = np.asarray(
        [(int(curve.first_point_index), int(curve.points_length)) for curve in curves_obj.data.curves],
        dtype=np.int64,
    )
    if spans.size == 0:
        raise ValueError("Hair Curves has no strands")
    if np.any(spans[:, 1] < 2):
        raise ValueError("Every strand must contain at least two points")
    expected = 0
    for start, count in spans:
        if int(start) != expected:
            raise ValueError("Curves points are not contiguous by strand")
        expected += int(count)
    return np.ascontiguousarray(spans)


def curve_offsets(curves_obj) -> np.ndarray:
    spans = curve_spans(curves_obj)
    offsets = np.empty(len(spans) + 1, dtype=np.int32)
    offsets[:-1] = spans[:, 0]
    offsets[-1] = int(spans[-1, 0] + spans[-1, 1])
    return np.ascontiguousarray(offsets)


def read_local_points(curves_obj) -> np.ndarray:
    attr = curves_obj.data.attributes.get("position")
    if attr is None or len(attr.data) == 0:
        raise ValueError("Hair has no point-domain position attribute")
    flat = np.empty(len(attr.data) * 3, dtype=np.float32)
    attr.data.foreach_get("vector", flat)
    result = np.ascontiguousarray(flat.reshape(-1, 3), dtype=np.float32)
    if not np.isfinite(result).all():
        raise ValueError("Hair contains NaN or Inf")
    return result


def write_local_points(curves_obj, local_points: np.ndarray) -> None:
    values = np.ascontiguousarray(local_points, dtype=np.float32)
    attr = curves_obj.data.attributes.get("position")
    if attr is None or values.shape != (len(attr.data), 3):
        raise ValueError("Hair position topology changed")
    if not np.isfinite(values).all():
        raise ValueError("Refusing to write NaN or Inf to Hair")
    attr.data.foreach_set("vector", values.ravel())
    curves_obj.data.update_tag()


def _points_to_world(local: np.ndarray, matrix_world) -> np.ndarray:
    matrix = np.asarray(matrix_world, dtype=np.float64)
    homogeneous = np.empty((len(local), 4), dtype=np.float64)
    homogeneous[:, :3] = local
    homogeneous[:, 3] = 1.0
    return np.ascontiguousarray((homogeneous @ matrix.T)[:, :3], dtype=np.float32)


def _read_data_world(data, matrix_world, expected: int) -> np.ndarray:
    attr = data.attributes.get("position")
    if attr is None or len(attr.data) != expected:
        raise ValueError("Evaluated Hair topology differs from source Hair")
    flat = np.empty(expected * 3, dtype=np.float32)
    attr.data.foreach_get("vector", flat)
    return _points_to_world(flat.reshape(-1, 3), matrix_world)


def sample_hair(curves_obj, depsgraph=None, *,
                curve_offsets_hint: np.ndarray | None = None) -> HairSample:
    local = read_local_points(curves_obj)
    if curve_offsets_hint is None:
        offsets = curve_offsets(curves_obj)
    else:
        offsets = np.asarray(curve_offsets_hint, dtype=np.int32)
        valid_hint = (
            offsets.ndim == 1 and len(offsets) >= 2
            and int(offsets[0]) == 0 and int(offsets[-1]) == len(local)
        )
        if not valid_hint:
            raise ValueError("Cached Hair curve offsets no longer match the source points")
        offsets = np.ascontiguousarray(offsets)
    depsgraph = depsgraph or bpy.context.evaluated_depsgraph_get()
    evaluated = curves_obj.evaluated_get(depsgraph)
    original_world = _points_to_world(local, curves_obj.matrix_world)
    evaluated_world = _read_data_world(evaluated.data, evaluated.matrix_world, len(local))
    return HairSample(
        evaluated_world=evaluated_world,
        original_world=original_world,
        modifier_offset_world=np.ascontiguousarray(evaluated_world - original_world, dtype=np.float32),
        local=local,
        curve_offsets=offsets,
    )


def world_to_local(curves_obj, world_points: np.ndarray, modifier_offset_world=None) -> np.ndarray:
    values = np.asarray(world_points, dtype=np.float64)
    if modifier_offset_world is not None:
        values = values - np.asarray(modifier_offset_world, dtype=np.float64)
    inverse = np.asarray(curves_obj.matrix_world.inverted(), dtype=np.float64)
    homogeneous = np.empty((len(values), 4), dtype=np.float64)
    homogeneous[:, :3] = values
    homogeneous[:, 3] = 1.0
    return np.ascontiguousarray((homogeneous @ inverse.T)[:, :3], dtype=np.float32)


def extract_mesh(obj, depsgraph=None) -> MeshSample:
    if obj is None:
        return MeshSample(np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.int32))
    if obj.type != "MESH":
        raise ValueError(f"{obj.name} is not a Mesh object")
    depsgraph = depsgraph or bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        if len(mesh.vertices) == 0 or len(mesh.polygons) == 0:
            raise ValueError(f"Collider {obj.name} has no evaluated polygons")
        flat_vertices = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
        mesh.vertices.foreach_get("co", flat_vertices)
        vertices = _points_to_world(flat_vertices.reshape(-1, 3), evaluated.matrix_world)
        # Blender's geometry-dependent quad tessellator can choose the other
        # diagonal as an animated quad deforms. ADMM-RS needs invariant triangle
        # indices for BVH refit, so triangulate each evaluated polygon by a
        # deterministic fan over its stable loop order.
        loop_vertices = np.empty(len(mesh.loops), dtype=np.int32)
        starts = np.empty(len(mesh.polygons), dtype=np.int32)
        totals = np.empty(len(mesh.polygons), dtype=np.int32)
        mesh.loops.foreach_get("vertex_index", loop_vertices)
        mesh.polygons.foreach_get("loop_start", starts)
        mesh.polygons.foreach_get("loop_total", totals)
        if np.any(totals < 3):
            raise ValueError(f"Collider {obj.name} contains a polygon with fewer than three vertices")
        triangle_groups: list[np.ndarray] = []
        for polygon_size in np.unique(totals):
            group_starts = starts[totals == polygon_size]
            polygon_vertices = loop_vertices[group_starts[:, None] + np.arange(int(polygon_size), dtype=np.int32)]
            for corner in range(1, int(polygon_size) - 1):
                triangle_groups.append(polygon_vertices[:, (0, corner, corner + 1)])
        triangles = np.ascontiguousarray(np.concatenate(triangle_groups, axis=0), dtype=np.int32)
        matrix = np.asarray(evaluated.matrix_world, dtype=np.float64)
        if float(np.linalg.det(matrix[:3, :3])) < 0.0:
            triangles = triangles[:, (0, 2, 1)]
        triangles = np.ascontiguousarray(triangles, dtype=np.int32)
        if not np.isfinite(vertices).all():
            raise ValueError(f"Collider {obj.name} contains NaN or Inf")
        return MeshSample(vertices, triangles)
    finally:
        evaluated.to_mesh_clear()


def has_mesh_cache_modifier(obj) -> bool:
    """Return whether a Mesh is animated by either Blender mesh-cache modifier."""
    return bool(
        obj is not None
        and obj.type == "MESH"
        and any(
            modifier.type in {"MESH_CACHE", "MESH_SEQUENCE_CACHE"}
            for modifier in obj.modifiers
        )
    )


def extract_deform_bones(obj, depsgraph=None, *, cache_fallback=None) -> GuideSample:
    """Read collider guide bones, allowing cached Clothes to share Body guides."""
    if obj is None:
        return GuideSample(np.empty((0, 2, 3), dtype=np.float32), (), "")
    if obj.type != "MESH":
        raise ValueError(f"{obj.name} is not a Mesh object")
    armature = obj.find_armature()
    if armature is None and cache_fallback is not None and has_mesh_cache_modifier(obj):
        if cache_fallback.type != "MESH":
            raise ValueError(f"{cache_fallback.name} is not a Mesh object")
        armature = cache_fallback.find_armature()
    if armature is None or armature.type != "ARMATURE":
        raise ValueError(f"Collider {obj.name} has no Armature Modifier")
    depsgraph = depsgraph or bpy.context.evaluated_depsgraph_get()
    evaluated = armature.evaluated_get(depsgraph)
    if evaluated.pose is None:
        raise ValueError(f"Armature {armature.name} has no evaluated pose")
    pose_bones = [
        bone for bone in evaluated.pose.bones
        if bool(bone.bone.use_deform) and float(bone.bone.length) > 1.0e-6
    ]
    if not pose_bones:
        raise ValueError(f"Armature {armature.name} has no non-degenerate deform bones")
    local = np.empty((len(pose_bones) * 2, 3), dtype=np.float32)
    for index, bone in enumerate(pose_bones):
        local[index * 2] = bone.head
        local[index * 2 + 1] = bone.tail
    world = _points_to_world(local, evaluated.matrix_world).reshape(-1, 2, 3)
    if not np.isfinite(world).all():
        raise ValueError(f"Armature {armature.name} contains NaN or Inf")
    return GuideSample(
        np.ascontiguousarray(world, dtype=np.float32),
        tuple(bone.name for bone in pose_bones),
        str(armature.name),
    )


def root_positions(points: np.ndarray, offsets: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(points[np.asarray(offsets[:-1], dtype=np.int64)], dtype=np.float32)


def pin_positions(points: np.ndarray, offsets: np.ndarray, pinned_rods: int) -> np.ndarray:
    """Leading ``pinned_rods + 1`` points of every strand, strand-major.

    These drive the kinematic leading rods. They come from the evaluated Curves,
    so they already follow the head through Surface Deform. Strands too short for
    the stride repeat their final point, which the solver clamps the same way.
    """
    starts = np.asarray(offsets[:-1], dtype=np.int64)
    lengths = np.asarray(offsets[1:], dtype=np.int64) - starts
    stride = int(pinned_rods) + 1
    local = np.minimum(np.arange(stride, dtype=np.int64)[None, :], (lengths - 1)[:, None])
    return np.ascontiguousarray(points[(starts[:, None] + local).reshape(-1)], dtype=np.float32)


def topology_digest(offsets: np.ndarray, body: MeshSample, clothes: MeshSample,
                    body_guides: GuideSample | None = None,
                    clothes_guides: GuideSample | None = None) -> str:
    digest = hashlib.sha256()
    for array in (offsets, body.triangles, clothes.triangles):
        contiguous = np.ascontiguousarray(array)
        digest.update(str(contiguous.shape).encode("ascii"))
        digest.update(contiguous.view(np.uint8))
    digest.update(str(body.vertices_world.shape).encode("ascii"))
    digest.update(str(clothes.vertices_world.shape).encode("ascii"))
    for guides in (body_guides, clothes_guides):
        if guides is not None:
            digest.update(guides.armature_name.encode("utf-8"))
            digest.update("\0".join(guides.names).encode("utf-8"))
            digest.update(str(guides.segments_world.shape).encode("ascii"))
    return digest.hexdigest()


def mesh_topology_diagnostics(sample: MeshSample) -> dict[str, int | float]:
    triangles = np.ascontiguousarray(sample.triangles, dtype=np.int32)
    vertices = np.ascontiguousarray(sample.vertices_world, dtype=np.float64)
    if len(triangles) == 0:
        return {
            "vertices": 0, "triangles": 0, "boundary_edges": 0,
            "non_manifold_edges": 0, "degenerate_triangles": 0,
            "signed_volume": 0.0,
        }
    edges = np.concatenate(
        (triangles[:, (0, 1)], triangles[:, (1, 2)], triangles[:, (2, 0)]), axis=0,
    )
    edges.sort(axis=1)
    _unique, counts = np.unique(edges, axis=0, return_counts=True)
    a, b, c = vertices[triangles[:, 0]], vertices[triangles[:, 1]], vertices[triangles[:, 2]]
    double_areas = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    signed_volume = float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)
    return {
        "vertices": int(len(vertices)),
        "triangles": int(len(triangles)),
        "boundary_edges": int(np.count_nonzero(counts == 1)),
        "non_manifold_edges": int(np.count_nonzero(counts > 2)),
        "degenerate_triangles": int(np.count_nonzero(double_areas <= 1.0e-12)),
        "signed_volume": signed_volume,
    }


def points_digest(points: np.ndarray) -> str:
    values = np.ascontiguousarray(points, dtype=np.float32)
    return hashlib.sha256(values.view(np.uint8)).hexdigest()


def force_viewport_refresh() -> None:
    bpy.context.view_layer.update()
    if bpy.app.background:
        return
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def validate_objects(hair, body, clothes=None) -> None:
    if hair is None or hair.type != "CURVES":
        raise ValueError("Select one Hair Curves object")
    if body is None or body.type != "MESH":
        raise ValueError("Select one closed Body Mesh object")
    if clothes is not None and clothes.type != "MESH":
        raise ValueError("Clothes must be a Mesh object or empty")
    if hair == body or hair == clothes or body == clothes:
        raise ValueError("Hair, Body, and Clothes must be different objects")
    curve_spans(hair)
