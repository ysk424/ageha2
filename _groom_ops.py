"""揚羽 — 前髪カット用の計測と長さ適用。

手順（Trim Bangs）
------------------
1. 垂れた髪（現在フレーム）でカット面との交点を計測し、
   (ストランド番号, カット後の長さ m) を一時配列に保持する。
2. フレーム 1 + キャッシュクリアで植え直後のウニへ戻す。
3. 一時配列の長さをウニ上のローカル座標へ適用する。

カット面は tokoya と同じ水平平面（眼 AABB + Side/Z 余白）。
"""
from __future__ import annotations

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import _mask_plant


def _read_local(curves_obj: bpy.types.Object) -> np.ndarray:
    attr = curves_obj.data.attributes.get("position")
    n = len(attr.data)
    flat = np.zeros(n * 3, dtype=np.float32)
    attr.data.foreach_get("vector", flat)
    return flat.reshape(n, 3)


def _write_local(curves_obj: bpy.types.Object, local_pts: np.ndarray) -> None:
    attr = curves_obj.data.attributes.get("position")
    attr.data.foreach_set("vector", local_pts.ravel().astype(np.float32))
    curves_obj.data.update_tag()


def _points_per_curve(curves_obj: bpy.types.Object) -> int:
    n_curves = len(curves_obj.data.curves)
    n_points = len(curves_obj.data.points)
    if n_curves <= 0 or n_points <= 0:
        raise RuntimeError("髪 Curves にストランドがありません")
    if n_points % n_curves:
        raise RuntimeError("すべてのストランドは同じ点数である必要があります")
    return n_points // n_curves


def _read_world_eval(curves_obj: bpy.types.Object) -> np.ndarray:
    deps = bpy.context.evaluated_depsgraph_get()
    eval_obj = curves_obj.evaluated_get(deps)
    attr = eval_obj.data.attributes.get("position")
    n = len(attr.data)
    flat = np.zeros(n * 3, dtype=np.float32)
    attr.data.foreach_get("vector", flat)
    local_pts = flat.reshape(n, 3)
    mw = np.array(eval_obj.matrix_world, dtype=np.float32)
    lh = np.column_stack([local_pts, np.ones(n, dtype=np.float32)])
    return (lh @ mw.T)[:, :3].astype(np.float32, copy=True)


def _build_bvh(ref_mesh_obj: bpy.types.Object) -> BVHTree:
    deps = bpy.context.evaluated_depsgraph_get()
    eval_obj = ref_mesh_obj.evaluated_get(deps)
    mesh = eval_obj.to_mesh()
    mat = eval_obj.matrix_world
    verts_w = [mat @ v.co for v in mesh.vertices]
    polys = [tuple(p.vertices) for p in mesh.polygons]
    bvh = BVHTree.FromPolygons(verts_w, polys)
    eval_obj.to_mesh_clear()
    return bvh


def _arc_length(pts_3d: np.ndarray) -> float:
    return float(np.sum(np.linalg.norm(np.diff(pts_3d, axis=0), axis=1)))


def _resample_polyline(pts_3d: np.ndarray, distances: list[float]) -> np.ndarray:
    arcs = np.zeros(len(pts_3d), dtype=np.float64)
    for index in range(1, len(pts_3d)):
        arcs[index] = arcs[index - 1] + float(
            np.linalg.norm(pts_3d[index] - pts_3d[index - 1])
        )
    total = arcs[-1]
    if total < 1.0e-9:
        return pts_3d.copy()

    result = np.empty_like(pts_3d)
    for out_index, distance in enumerate(distances):
        target = min(total, max(0.0, float(distance)))
        seg = int(np.searchsorted(arcs, target, side="right") - 1)
        seg = max(0, min(seg, len(pts_3d) - 2))
        span = arcs[seg + 1] - arcs[seg]
        t = 0.0 if span <= 1.0e-9 else (target - arcs[seg]) / span
        result[out_index] = pts_3d[seg] * (1.0 - t) + pts_3d[seg + 1] * t
    return result


def _ray_cast_bidir(bvh: BVHTree, p0: Vector, p1: Vector):
    d = p1 - p0
    seg_len = d.length
    if seg_len < 1e-8:
        return None, None
    fwd = d.normalized()

    loc, _, _, dist = bvh.ray_cast(p0, fwd, seg_len)
    if loc is not None:
        return dist, loc

    loc_r, _, _, dist_r = bvh.ray_cast(p1, -fwd, seg_len)
    if loc_r is not None:
        return seg_len - dist_r, loc_r

    return None, None


def measure_bangs_cut_lengths(
    curves_obj: bpy.types.Object,
    cutter_obj: bpy.types.Object,
) -> list[tuple[int, float]]:
    """垂れた髪の評価ワールド座標でカット長を計測する。

    戻り値: (curve_index, new_length_m) のリスト。
    交点のないストランドは含めない。
    """
    bvh = _build_bvh(cutter_obj)
    local = _read_local(curves_obj)
    world = _read_world_eval(curves_obj)
    ppc = _points_per_curve(curves_obj)
    n_c = len(local) // ppc
    cuts: list[tuple[int, float]] = []

    for ci in range(n_c):
        b = ci * ppc
        arcs = np.zeros(ppc, dtype=np.float64)
        for j in range(1, ppc):
            arcs[j] = arcs[j - 1] + float(
                np.linalg.norm(world[b + j] - world[b + j - 1])
            )
        total = arcs[-1]
        if total < 1e-6:
            continue

        all_hits: list[float] = []
        for seg in range(ppc - 1):
            p0 = Vector(world[b + seg].tolist())
            p1 = Vector(world[b + seg + 1].tolist())
            dist, _ = _ray_cast_bidir(bvh, p0, p1)
            if dist is not None:
                all_hits.append(arcs[seg] + dist)

        if not all_hits:
            continue
        hit_arc = min(all_hits)
        if hit_arc >= total:
            continue

        # 物理で弧長はほぼ保存される。カット長はワールド弧上の根からの距離。
        # ローカル弧長との比でスケールし、わずかな誤差を吸収する。
        local_len = _arc_length(local[b : b + ppc])
        scale = hit_arc / total
        new_length = local_len * scale
        if new_length < 0.0:
            continue
        if new_length >= local_len - 1.0e-9:
            continue
        cuts.append((ci, float(new_length)))

    return cuts


def apply_strand_lengths(
    curves_obj: bpy.types.Object,
    cuts: list[tuple[int, float]],
) -> int:
    """ウニ状態のローカル髪へ、記録したカット長を適用する。"""
    if not cuts:
        return 0

    local = _read_local(curves_obj)
    ppc = _points_per_curve(curves_obj)
    n_c = len(local) // ppc
    rest_lengths = [
        _arc_length(local[ci * ppc : ci * ppc + ppc]) for ci in range(n_c)
    ]
    max_length = max(rest_lengths) if rest_lengths else 0.0
    applied = 0

    for ci, new_length in cuts:
        if ci < 0 or ci >= n_c:
            continue
        b = ci * ppc
        rest = rest_lengths[ci]
        length = max(0.0, min(float(new_length), rest))
        if length >= rest - 1.0e-9:
            continue
        distances = _mask_plant.natural_distances(length, max_length, ppc)
        local[b : b + ppc] = _resample_polyline(local[b : b + ppc], distances)
        applied += 1

    if applied:
        _write_local(curves_obj, local)
    return applied
