"""Independent FP64 NumPy oracle for isolated production CUDA kernels."""

import unittest, sys, tempfile, json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "extension"))
from native import Solver, Collider, parameters, parameter_hash
import cache


def bending_oracle(rest, x, v, fixed, p, dt, target):
    n = len(x)
    length = np.linalg.norm(np.diff(rest, axis=0), axis=1)
    mass = np.zeros(n)
    mass[:-1] += length * p["linear_density"] / 2
    mass[1:] += length * p["linear_density"] / 2
    q = np.zeros((n - 2, n))
    for i in range(1, n - 1):
        l, r = length[i - 1 : i + 1]
        avg = (l + r) / 2
        q[i - 1, i - 1 : i + 2] = [1 / (avg * l), -(1 / l + 1 / r) / avg, 1 / (avg * r)]
    h = dt / p["substeps"]
    kb = q.T @ np.diag(p["bending_rigidity"] * (length[:-1] + length[1:]) / 2) @ q
    a = np.diag(mass) + h * h * kb
    rhs = mass[:, None] * (
        x + h * np.exp(-p["damping"] * h) * v + h * h * np.array([0, 0, -p["gravity"]])
    )
    free = np.flatnonzero(~fixed.astype(bool))
    pin = np.flatnonzero(fixed)
    out = target.copy().astype(float)
    out[free] = np.linalg.solve(
        a[np.ix_(free, free)], rhs[free] - a[np.ix_(free, pin)] @ target[pin]
    )
    return out


def length_oracle(rest, x, fixed, p):
    n = len(x)
    l = np.linalg.norm(np.diff(rest, axis=0), axis=1)
    m = np.zeros(n)
    m[:-1] += l * p["linear_density"] / 2
    m[1:] += l * p["linear_density"] / 2
    w = np.where(fixed, 0, 1 / m)
    delta = np.diff(x, axis=0)
    length = np.linalg.norm(delta, axis=1)
    t = delta / length[:, None]
    j = np.zeros((n - 1, 3 * n))
    for i in range(n - 1):
        j[i, i * 3 : i * 3 + 3] = -t[i]
        j[i, (i + 1) * 3 : (i + 2) * 3] = t[i]
    ww = np.repeat(w, 3)
    a = (j * ww) @ j.T
    a += np.diag((w[:-1] + w[1:]) * p["length_regularization_relative"])
    lam = np.linalg.solve(a, l - length)
    return x + (ww * (j.T @ lam)).reshape(n, 3)


class TestOracle(unittest.TestCase):
    def setUp(self):
        self.p = parameters()
        self.solvers = []

    def tearDown(self):
        for s in self.solvers:
            s.close()

    def solver(self, x, fixed=None, dt=1 / 240):
        s = Solver(x, [0, len(x)], fixed, self.p, dt=dt)
        self.solvers.append(s)
        return s

    def assert_rms(self, actual, expected, tol=1e-5):
        rms = float(np.sqrt(np.mean((actual - expected) ** 2)))
        self.assertLessEqual(rms, tol)
        return rms

    def test_implicit_bending_nonuniform_pinned(self):
        rng = np.random.default_rng(5)
        x = np.c_[
            np.cumsum(rng.uniform(0.02, 0.05, 17)),
            rng.normal(0, 0.005, 17),
            rng.normal(0, 0.003, 17),
        ].astype(np.float32)
        v = rng.normal(0, 0.1, x.shape).astype(np.float32)
        fixed = np.zeros(17, np.uint8)
        fixed[[0, 1, -1]] = 1
        s = self.solver(x, fixed)
        s.set_state(x, v)
        target = x.copy()
        target[0] += [0.001, 0.002, 0]
        expected = bending_oracle(
            x.astype(float), x.astype(float), v.astype(float), fixed, self.p, 1 / 240, target
        )
        s.probe(0, target)
        self.assert_rms(s.x, expected)

    def test_chain_length_nonuniform(self):
        x = np.c_[
            np.linspace(0, 1, 23), 0.05 * np.sin(np.linspace(0, np.pi, 23)), np.zeros(23)
        ].astype(np.float32)
        fixed = np.zeros(23, np.uint8)
        fixed[0] = 1
        s = self.solver(x, fixed)
        current = x.copy()
        current[1:] += np.random.default_rng(9).normal(0, 0.001, (22, 3))
        s.set_state(current, np.zeros_like(x))
        expected = length_oracle(x.astype(float), current.astype(float), fixed, self.p)
        s.probe(1)
        self.assert_rms(s.x, expected)

    def test_projection_all_shapes(self):
        for kind in range(4):
            with self.subTest(kind=kind):
                x = np.array(
                    [[0.05, 0.01, 0.02], [0.06, 0.02, 0.03], [0.07, 0.02, -0.01]], np.float32
                )
                s = self.solver(x)
                c = Collider(kind, 3, radius=0.12, half_length=0.03)
                expected = x.copy().astype(float)
                if kind == 0:
                    expected[:, 2] = np.maximum(expected[:, 2], self.p["guide_radius"])
                else:
                    q = expected.copy()
                    if kind == 2:
                        q[:, 2] -= np.clip(q[:, 2], -0.03, 0.03)
                    if kind == 3:
                        q[:, 2] = 0
                    dist = np.linalg.norm(q, axis=1)
                    expected += (
                        q
                        / dist[:, None]
                        * np.maximum(0, 0.12 + self.p["guide_radius"] - dist)[:, None]
                    )
                s.probe(2, colliders=[c])
                self.assert_rms(s.x, expected)

    def test_coulomb_impulse(self):
        r = self.p["guide_radius"]
        x = np.array([[0, 0, r], [0.01, 0, r], [0.02, 0, r]], np.float32)
        s = self.solver(x)
        velocity = np.array([[0.1, 0.2, -0.3], [0.2, 0, -0.1], [0, 0, -0.2]], np.float32)
        s.set_state(x, velocity)
        c = Collider(0, 1, friction=self.p["friction"])
        s.probe(2, colliders=[c])
        s.probe(4, colliders=[c])
        expected = velocity.copy()
        tangent = np.linalg.norm(velocity[:, :2], axis=1)
        factor = np.maximum(
            0, 1 - self.p["friction"] * (-velocity[:, 2]) / np.maximum(tangent, 1e-30)
        )
        expected[:, :2] *= factor[:, None]
        expected[:, 2] = 0
        self.assert_rms(s.v, expected)
        data = s.contact_data()[:, 0]
        self.assertTrue(
            np.all(np.linalg.norm(data[:, 4:7], axis=1) <= data[:, 3] * data[:, 1] + 1e-12)
        )

    def test_rigid_translation_equivariance(self):
        x = np.c_[np.linspace(0, 0.05, 11), np.zeros(11), np.ones(11)].astype(np.float32)
        fixed = np.zeros(11, np.uint8)
        fixed[0] = 1
        a = self.solver(x, fixed, 1 / 24)
        shift = np.array([0.1, -0.2, 0.3], np.float32)
        b = self.solver(x + shift, fixed, 1 / 24)
        a.step(x)
        b.step(x + shift)
        self.assert_rms(b.x - a.x, np.broadcast_to(shift, x.shape), 2e-5)

    def test_cache_crc_and_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            x = np.zeros((3, 3), np.float32)
            off = np.array([0, 3], np.uint32)
            m = cache.create(directory, x, off, self.p, parameter_hash(self.p))
            cache.write(directory, 7, x, m)
            self.assertTrue(
                np.array_equal(
                    cache.read(directory, 7, m["topology_hash"], m["parameter_hash"], 3), x
                )
            )
            with self.assertRaises(ValueError):
                cache.read(directory, 7, m["topology_hash"], "0" * 64, 3)
            path = Path(directory) / "frame_000007.k4c"
            data = bytearray(path.read_bytes())
            data[-1] ^= 1
            path.write_bytes(data)
            with self.assertRaises(ValueError):
                cache.read(directory, 7, m["topology_hash"], m["parameter_hash"], 3)

    def test_duplicate_normalization_preserves_endpoints_count(self):
        x = np.array([[0, 0, 0], [0, 0, 0], [0.2, 0, 0], [0.3, 0.1, 0]], np.float32)
        s = self.solver(x)
        self.assertEqual(s.repaired, [0])
        self.assertEqual(s.x.shape, x.shape)
        np.testing.assert_array_equal(s.x[[0, -1]], x[[0, -1]])
        self.assertTrue((np.linalg.norm(np.diff(s.x, axis=0), axis=1) > 0).all())

    def test_budget_rejected(self):
        p = dict(self.p, substeps=64)
        with self.assertRaises(RuntimeError):
            Solver([[0, 0, 0], [0.01, 0, 0]], [0, 2], p=p)

    def test_all_topology_buckets(self):
        for n in (2, 8, 16, 32, 33, 64, 65, 128, 129, 256):
            with self.subTest(points=n):
                t = np.linspace(0, 1, n)
                x = np.c_[t, 0.02 * np.sin(t * np.pi), 0.005 * np.cos(t * np.pi)].astype(np.float32)
                fixed = np.zeros(n, np.uint8)
                fixed[0] = 1
                s = self.solver(x, fixed)
                expected = bending_oracle(
                    x.astype(float), x.astype(float), np.zeros_like(x), fixed, self.p, 1 / 240, x
                )
                s.probe(0, x)
                self.assert_rms(s.x, expected)
                current = x.copy()
                current[1:, 0] += 0.0001 * np.sin(t[1:] * 10)
                s.set_state(current, np.zeros_like(x))
                expected = length_oracle(x.astype(float), current.astype(float), fixed, self.p)
                s.probe(1)
                self.assert_rms(s.x, expected)

    def test_small_hair_bending_precision(self):
        q = np.c_[
            np.linspace(0, 0.033, 11), 0.001 * np.sin(np.linspace(0, 2, 11)), np.full(11, 1.6)
        ].astype(np.float32)
        fixed = np.zeros(11, np.uint8)
        fixed[0] = 1
        s = self.solver(q, fixed, 1 / 24)
        expected = bending_oracle(
            q.astype(float), q.astype(float), np.zeros_like(q), fixed, self.p, 1 / 24, q
        )
        s.probe(0, q)
        length = np.linalg.norm(np.diff(q, axis=0), axis=1).sum()
        self.assertLess(np.sqrt(np.mean((s.x - expected) ** 2)) / length, 1e-5)

    def test_mesh_projection_uses_original_triangles(self):
        r = self.p["guide_radius"]
        x = np.array([[0, 0, r / 2], [0.01, 0, r / 3], [0.02, 0, r / 4]], np.float32)
        s = self.solver(x)
        verts = np.array([[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0]], np.float32)
        tri = np.array([[0, 1, 2], [0, 2, 3]], np.uint32)
        s.set_mesh(verts, tri)
        s.probe(2)
        self.assert_rms(s.x, np.c_[x[:, :2], np.full(3, r)])

    def test_repaired_fixed_tangent_targets(self):
        x = np.array([[0, 0, 0], [0.16, 0, 0]] + [[0.36, 0.1, 0]] * 9, np.float32)
        fixed = np.zeros(11, np.uint8)
        fixed[:2] = 1
        s = self.solver(x, fixed)
        initial = s.x.copy()
        rotation = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]], np.float32)
        translation = np.array([0.01, 0.02, 0], np.float32)
        target = x @ rotation.T + translation
        s.step(target)
        np.testing.assert_allclose(
            s.x[:2], (initial @ rotation.T + translation)[:2], atol=1e-7, rtol=0
        )

    def test_full_unconstrained_substep_path(self):
        x = np.c_[np.linspace(0, 1, 11), 0.02 * np.sin(np.linspace(0, 2, 11)), np.zeros(11)].astype(
            np.float32
        )
        fixed = np.zeros(11, np.uint8)
        fixed[0] = 1
        s = self.solver(x, fixed)
        v = np.random.default_rng(12).normal(0, 0.1, x.shape).astype(np.float32)
        s.set_state(x, v)
        target = x.copy()
        target[0] += [0.001, 0.002, 0]
        expected = x.astype(float)
        velocity = v.astype(float)
        h = (1 / 240) / self.p["substeps"]
        for sub in range(self.p["substeps"]):
            old = expected.copy()
            kin = x + (target - x) * (sub + 1) / self.p["substeps"]
            expected = bending_oracle(
                x.astype(float), expected, velocity, fixed, self.p, 1 / 240, kin
            )
            for _ in range(self.p["length_passes"]):
                expected = length_oracle(x.astype(float), expected, fixed, self.p)
            velocity = (expected - old) / h
        s.step(target)
        self.assert_rms(s.x, expected, 1e-5)
        self.assertLess(np.sqrt(np.mean((s.v - velocity) ** 2)) / (1 / (1 / 240)), 1e-5)

    def test_animated_plane_surface_velocity(self):
        p = dict(self.p, gravity=0.0, damping=0.0, bending_rigidity=0.0)
        r = p["guide_radius"]
        x = np.array([[0, 0, r], [0.01, 0, r], [0.02, 0, r]], np.float32)
        s = Solver(x, [0, 3], p=p, max_colliders=1)
        self.solvers.append(s)
        old = Collider(0, 1, center=(0, 0, 0), friction=0)
        new = Collider(0, 1, center=(0, 0, 0.001), friction=0)
        s.step(x, [new], [old])
        self.assert_rms(s.x[:, 2], np.full(3, 0.001 + r))
        self.assert_rms(s.v[:, 2], np.full(3, 0.024))

    def test_collider_count_cannot_change_after_prepare(self):
        x = np.array([[0, 0, 0.01], [0.01, 0, 0.01]], np.float32)
        s = self.solver(x)
        s.step(x, [Collider(0, 0)])
        with self.assertRaises(ValueError):
            s.step(x, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
