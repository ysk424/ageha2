"""Checked ctypes interface. CUDA errors are never replaced by a CPU solve."""

from pathlib import Path
import ctypes as C
import hashlib
import json
import time
import numpy as np

ROOT = Path(__file__).resolve().parent
F3 = C.c_float * 3
F4 = C.c_float * 4


class Config(C.Structure):
    _fields_ = (
        [(n, C.c_float) for n in ("dt", "bending", "density", "radius", "damping", "friction")]
        + [("gravity", F3)]
        + [(n, C.c_float) for n in ("regularization", "contact_tolerance")]
        + [(n, C.c_int) for n in ("substeps", "passes", "impulses")]
        + [("plane_axis", C.c_int), ("plane_coordinate", C.c_float)]
    )


class Collider(C.Structure):
    _fields_ = [
        ("type", C.c_int),
        ("id", C.c_int),
        ("center", F3),
        ("rotation", F4),
        ("radius", C.c_float),
        ("half_length", C.c_float),
        ("friction", C.c_float),
    ]

    def __init__(
        self,
        kind=0,
        id=0,
        center=(0, 0, 0),
        rotation=(1, 0, 0, 0),
        radius=0.12,
        half_length=0,
        friction=0.35,
    ):
        super().__init__(kind, id, F3(*center), F4(*rotation), radius, half_length, friction)


class Stats(C.Structure):
    _fields_ = (
        [(n, C.c_double) for n in ("native_ms", "upload_ms", "download_ms")]
        + [
            (n, C.c_float)
            for n in (
                "max_length_error",
                "p99_length_error",
                "min_gap",
                "chord_bound",
                "max_displacement",
                "max_normal_impulse",
                "max_tangent_impulse",
                "friction_cone_violation",
            )
        ]
        + [
            (n, C.c_uint32)
            for n in (
                "points",
                "strands",
                "contacts",
                "motion_violations",
                "nonfinite",
                "overflow",
                "frame_allocations",
                "launches",
            )
        ]
    )

    def as_dict(self):
        return {name: getattr(self, name) for name, _ in self._fields_}


def parameters(path=None):
    return json.loads(Path(path or ROOT / "parameters.json").read_text(encoding="utf8"))


def parameter_hash(p):
    return hashlib.sha256(json.dumps(p, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def array(a, dtype=np.float32):
    return np.ascontiguousarray(a, dtype=dtype)


def ptr(a):
    return a.ctypes.data_as(C.c_void_p) if a is not None else None


def normalize(positions, offsets):
    p = array(positions).copy()
    repaired = []
    for strand, (a, b) in enumerate(zip(offsets[:-1], offsets[1:])):
        segment = p[a:b].astype(np.float64)
        dist = np.r_[0, np.cumsum(np.linalg.norm(np.diff(segment, axis=0), axis=1))]
        if np.all(np.diff(dist) > 1e-8):
            continue
        if dist[-1] <= 1e-8:
            raise ValueError(f"Strand {strand} is entirely collapsed; no strand is dropped")
        keep = np.r_[True, np.diff(dist) > 1e-8]
        d = dist[keep]
        q = segment[keep]
        sample = np.linspace(0, dist[-1], len(segment))
        p[a:b] = np.column_stack([np.interp(sample, d, q[:, j]) for j in range(3)])
        p[a] = segment[0]
        p[b - 1] = segment[-1]
        repaired.append(int(strand))
    return p, repaired


_lib = None


def library():
    global _lib
    if _lib:
        return _lib
    lib = C.CDLL(str(ROOT / "bin/kami4_hair_core.dll"))
    P = C.c_void_p
    I = C.c_int
    lib.k4_create.argtypes = [C.POINTER(Config), I, I, P, P, P, I, C.POINTER(P)]
    lib.k4_set_mesh.argtypes = [P, I, P, I, P]
    lib.k4_prepare.argtypes = [P, I]
    lib.k4_step.argtypes = [P, P, P, P, I, P, P, C.POINTER(Stats)]
    lib.k4_download.argtypes = [P, P, P]
    lib.k4_set_state.argtypes = [P, P, P]
    lib.k4_contact_data.argtypes = [P, P]
    lib.k4_point_data.argtypes = [P, P]
    lib.k4_probe.argtypes = [P, I, P, P, I]
    lib.k4_destroy.argtypes = [P]
    lib.k4_destroy.restype = None
    lib.k4_error.restype = C.c_char_p
    lib.k4_version.restype = C.c_char_p
    _lib = lib
    return lib


class Solver:
    def __init__(
        self,
        positions,
        offsets,
        fixed=None,
        p=None,
        dt=1 / 24,
        gravity=(0, 0, -1),
        max_colliders=8,
        plane_axis=-1,
    ):
        self.lib = library()
        self.handle = C.c_void_p()
        self.p = p or parameters()
        self.x, self.repaired = normalize(positions, offsets)
        self.offsets = array(offsets, np.uint32)
        self.v = np.zeros_like(self.x)
        self.fixed = np.zeros(len(self.x), np.uint8) if fixed is None else array(fixed, np.uint8)
        if self.x.ndim != 2 or self.x.shape[1] != 3 or len(self.fixed) != len(self.x):
            raise ValueError("Invalid point arrays")
        if not np.isfinite(self.x).all():
            raise ValueError("Nonfinite input")
        self.repair_target_map = []
        raw = array(positions)
        for strand in self.repaired:
            a, b = map(int, self.offsets[strand : strand + 2])
            arc = np.r_[
                0, np.cumsum(np.linalg.norm(np.diff(raw[a:b].astype(float), axis=0), axis=1))
            ]
            for local in np.flatnonzero(self.fixed[a:b]):
                if local == 0 or local == b - a - 1:
                    continue
                distance = arc[-1] * local / (b - a - 1)
                edge = min(int(np.searchsorted(arc, distance, side="right") - 1), b - a - 2)
                weight = (distance - arc[edge]) / (arc[edge + 1] - arc[edge])
                self.repair_target_map.append(
                    (a + int(local), a + edge, a + edge + 1, float(weight))
                )
        self.config = Config(
            dt,
            self.p["bending_rigidity"],
            self.p["linear_density"],
            self.p["guide_radius"],
            self.p["damping"],
            self.p["friction"],
            F3(*(np.asarray(gravity) * self.p["gravity"])),
            self.p["length_regularization_relative"],
            self.p["contact_tolerance"],
            self.p["substeps"],
            self.p["length_passes"],
            self.p["impulse_sweeps"],
            plane_axis,
            0,
        )
        self.check(
            self.lib.k4_create(
                C.byref(self.config),
                len(self.x),
                len(self.offsets) - 1,
                ptr(self.x),
                ptr(self.offsets),
                ptr(self.fixed),
                max_colliders,
                C.byref(self.handle),
            )
        )
        self.mesh_count = 0
        self.mesh_triangles = None
        self.slots = max_colliders + 1
        self.prepared_count = None

    def check(self, code):
        if code:
            raise RuntimeError(f"K4 error {code}: {self.lib.k4_error().decode()}")

    def set_mesh(self, vertices, triangles):
        vertices = array(vertices)
        triangles = array(triangles, np.uint32)
        self.check(
            self.lib.k4_set_mesh(
                self.handle, len(vertices), ptr(vertices), len(triangles), ptr(triangles)
            )
        )
        self.mesh_count = len(vertices)
        self.mesh_triangles = triangles

    def prepare(self, count):
        self.check(self.lib.k4_prepare(self.handle, count))
        self.prepared_count = count

    def step(
        self,
        targets=None,
        colliders=(),
        previous_colliders=None,
        mesh_previous=None,
        mesh_next=None,
        download=True,
    ):
        if self.prepared_count is None:
            self.prepare(len(colliders))
        if self.prepared_count != len(colliders):
            raise ValueError("Collider count changed; reinitialize")
        if previous_colliders is not None and len(previous_colliders) != len(colliders):
            raise ValueError("Collider count changed; reinitialize")
        supplied_targets = targets is not None
        targets = array(self.x if targets is None else targets)
        if supplied_targets and self.repair_target_map:
            raw_targets = targets
            targets = targets.copy()
            for index, a, b, weight in self.repair_target_map:
                targets[index] = raw_targets[a] * (1 - weight) + raw_targets[b] * weight
        if targets.shape != self.x.shape or not np.isfinite(targets).all():
            raise ValueError("Invalid root targets")
        a = (Collider * len(colliders))(
            *(colliders if previous_colliders is None else previous_colliders)
        )
        b = (Collider * len(colliders))(*colliders)
        m0 = array(mesh_previous) if mesh_previous is not None else None
        m1 = array(mesh_next) if mesh_next is not None else None
        if self.mesh_count and (
            m0 is None or m1 is None or m0.shape != (self.mesh_count, 3) or m1.shape != m0.shape
        ):
            raise ValueError("Mesh topology changed/missing")
        if self.mesh_count and (not np.isfinite(m0).all() or not np.isfinite(m1).all()):
            raise ValueError("Nonfinite collider animation")
        stats = Stats()
        self.check(
            self.lib.k4_step(
                self.handle, ptr(targets), a, b, len(b), ptr(m0), ptr(m1), C.byref(stats)
            )
        )
        if download:
            began = time.perf_counter()
            self.download()
            stats.download_ms += (time.perf_counter() - began) * 1000
        return stats.as_dict()

    def download(self):
        self.check(self.lib.k4_download(self.handle, ptr(self.x), ptr(self.v)))
        return self.x

    def contact_data(self):
        data = np.empty((len(self.x), self.slots, 13), np.float32)
        self.check(self.lib.k4_contact_data(self.handle, ptr(data)))
        return data

    def point_data(self):
        data = np.empty((len(self.x), 8), np.float32)
        self.check(self.lib.k4_point_data(self.handle, ptr(data)))
        return data

    def probe(self, mode, target=None, colliders=()):
        target = array(target) if target is not None else None
        cols = (Collider * len(colliders))(*colliders)
        self.check(self.lib.k4_probe(self.handle, mode, ptr(target), cols, len(cols)))
        self.download()

    def set_state(self, x, v):
        x = array(x)
        v = array(v)
        if x.shape != self.x.shape or v.shape != x.shape:
            raise ValueError("State shape mismatch")
        self.check(self.lib.k4_set_state(self.handle, ptr(x), ptr(v)))
        self.x[:] = x
        self.v[:] = v

    def close(self):
        if getattr(self, "handle", None):
            self.lib.k4_destroy(self.handle)
            self.handle = C.c_void_p()

    def __del__(self):
        self.close()
