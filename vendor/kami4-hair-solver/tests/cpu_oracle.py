"""Independent FP64 validation backend. Never imported by the Blender runtime."""

import time
import numpy as np
from scipy.linalg import cho_factor, cho_solve, solve_banded
from native import parameters


class CPUOracle:
    def __init__(
        self,
        x,
        offsets,
        fixed=None,
        p=None,
        dt=1 / 24,
        gravity=(0, 0, -1),
        max_colliders=8,
        plane_axis=-1,
    ):
        assert len(offsets) == 2, "Oracle is for one small strand"
        self.p = p or parameters()
        self.x = np.asarray(x, dtype=float).copy()
        self.v = np.zeros_like(self.x)
        self.previous = self.x.copy()
        self.fixed = np.asarray(fixed, dtype=bool) if fixed is not None else np.zeros(len(x), bool)
        self.free = np.flatnonzero(~self.fixed)
        self.pin = np.flatnonzero(self.fixed)
        self.dt = dt
        self.h = dt / self.p["substeps"]
        self.plane_axis = plane_axis
        self.g = np.asarray(gravity) * self.p["gravity"]
        self.slots = max_colliders + 1
        self.rest = np.linalg.norm(np.diff(self.x, axis=0), axis=1)
        self.mass = np.zeros(len(x))
        self.mass[:-1] += self.rest * self.p["linear_density"] / 2
        self.mass[1:] += self.rest * self.p["linear_density"] / 2
        self.w = np.where(self.fixed, 0, 1 / self.mass)
        q = np.zeros((len(x) - 2, len(x)))
        for i in range(1, len(x) - 1):
            l, r = self.rest[i - 1 : i + 1]
            avg = (l + r) / 2
            q[i - 1, i - 1 : i + 2] = [1 / (avg * l), -(1 / l + 1 / r) / avg, 1 / (avg * r)]
        self.A = np.diag(self.mass) + self.h**2 * (
            q.T @ np.diag(self.p["bending_rigidity"] * (self.rest[:-1] + self.rest[1:]) / 2) @ q
        )
        self.factor = cho_factor(self.A[np.ix_(self.free, self.free)])
        self.contacts = np.zeros((len(x), self.slots, 13))
        self.contacts[:, :, 0] = -1

    def close(self):
        pass

    def set_state(self, x, v):
        self.x = np.asarray(x, dtype=float).copy()
        self.v = np.asarray(v, dtype=float).copy()
        self.previous = self.x.copy()

    def contact_data(self):
        return self.contacts.copy()

    def geometry(self, x, col):
        center = np.array(col.center, dtype=float)
        q = np.array(col.rotation, dtype=float)
        q /= np.linalg.norm(q)
        w, a, b, c = q
        rot = np.array(
            [
                [1 - 2 * (b * b + c * c), 2 * (a * b - c * w), 2 * (a * c + b * w)],
                [2 * (a * b + c * w), 1 - 2 * (a * a + c * c), 2 * (b * c - a * w)],
                [2 * (a * c - b * w), 2 * (b * c + a * w), 1 - 2 * (a * a + b * b)],
            ]
        )
        local = (x - center) @ rot
        if col.type == 0:
            gap = local[:, 2] - self.p["guide_radius"]
            normal = np.broadcast_to(rot[:, 2], x.shape).copy()
        else:
            direction = local.copy()
            if col.type == 2:
                direction[:, 2] -= np.clip(direction[:, 2], -col.half_length, col.half_length)
            if col.type == 3:
                direction[:, 2] = 0
            length = np.linalg.norm(direction, axis=1)
            normal = (direction / np.maximum(length[:, None], 1e-30)) @ rot.T
            gap = length - col.radius - self.p["guide_radius"]
        return gap, normal

    def project(self, cols):
        for k, col in enumerate(cols):
            gap, normal = self.geometry(self.x, col)
            active = (gap <= self.p["contact_tolerance"]) & ~self.fixed
            c = self.contacts[:, k]
            changed = c[:, 0] != col.id
            c[changed, 1:7] = 0
            c[~active] = 0
            c[~active, 0] = -1
            c[active, 0] = col.id
            c[active, 3] = col.friction
            c[active, 7:10] = normal[active]
            delta = np.maximum(-gap, 0)
            delta[~active] = 0
            self.x += normal * delta[:, None]
            c[self.free, 2] += delta[self.free] / (self.h * self.w[self.free])
        if self.plane_axis >= 0:
            self.x[:, self.plane_axis] = 0

    def step(self, targets=None, colliders=(), previous_colliders=None, **kwargs):
        start = time.perf_counter()
        target = np.asarray(targets if targets is not None else self.x, dtype=float)
        n = len(self.x)
        st = dict(
            native_ms=0.0,
            upload_ms=0.0,
            download_ms=0.0,
            max_length_error=0.0,
            p99_length_error=0.0,
            min_gap=1e20,
            chord_bound=0.0,
            max_displacement=0.0,
            max_normal_impulse=0.0,
            max_tangent_impulse=0.0,
            friction_cone_violation=0.0,
            points=n,
            strands=1,
            contacts=0,
            motion_violations=0,
            nonfinite=0,
            overflow=0,
            frame_allocations=0,
            launches=0,
        )
        max_errors = np.zeros(n - 1)
        for sub in range(self.p["substeps"]):
            old = self.x.copy()
            self.contacts[:, :, 2] = 0
            t = (sub + 1) / self.p["substeps"]
            fixed_target = (1 - t) * self.previous + t * target
            y = self.x + self.h * np.exp(-self.p["damping"] * self.h) * self.v + self.h**2 * self.g
            rhs = self.mass[:, None] * y
            self.x[self.pin] = fixed_target[self.pin]
            self.x[self.free] = cho_solve(
                self.factor,
                rhs[self.free] - self.A[np.ix_(self.free, self.pin)] @ fixed_target[self.pin],
            )
            for _ in range(self.p["length_passes"]):
                delta = np.diff(self.x, axis=0)
                length = np.linalg.norm(delta, axis=1)
                direction = delta / np.maximum(length[:, None], 1e-30)
                diag = (self.w[:-1] + self.w[1:]) * (1 + self.p["length_regularization_relative"])
                off = -self.w[1:-1] * np.sum(direction[:-1] * direction[1:], axis=1)
                rhs = self.rest - length
                zero = diag == 0
                diag[zero] = 1
                rhs[zero] = 0
                band = np.zeros((3, n - 1))
                band[1] = diag
                band[0, 1:] = off
                band[2, :-1] = off
                lam = solve_banded((1, 1), band, rhs, check_finite=False)
                dx = np.zeros_like(self.x)
                dx[:-1] -= direction * lam[:, None]
                dx[1:] += direction * lam[:, None]
                self.x += self.w[:, None] * dx
                self.project(colliders)
            self.project(colliders)
            self.v = (self.x - old) / self.h
            for k, col in enumerate(colliders):
                c = self.contacts[:, k]
                active = c[:, 0] >= 0
                normal = c[:, 7:10]
                jt = c[:, 4:7]
                jt -= normal * np.sum(jt * normal, axis=1)[:, None]
                mag = np.linalg.norm(jt, axis=1)
                cap = c[:, 3] * c[:, 1]
                jt *= np.minimum(1, cap / np.maximum(mag, 1e-30))[:, None]
                self.v[active] += (normal * (c[:, 1] - c[:, 2])[:, None] + jt)[active] * self.w[
                    active, None
                ]
            for _ in range(self.p["impulse_sweeps"]):
                for k, col in enumerate(colliders):
                    c = self.contacts[:, k]
                    ids = np.flatnonzero(c[:, 0] >= 0)
                    normal = c[ids, 7:10]
                    w = self.w[ids]
                    velocity = self.v[ids]
                    jn = np.maximum(0, c[ids, 1] - np.sum(velocity * normal, axis=1) / w)
                    velocity += normal * ((jn - c[ids, 1]) * w)[:, None]
                    jt = (
                        c[ids, 4:7]
                        - (velocity - normal * np.sum(velocity * normal, axis=1)[:, None])
                        / w[:, None]
                    )
                    mag = np.linalg.norm(jt, axis=1)
                    cap = c[ids, 3] * jn
                    jt *= np.minimum(1, cap / np.maximum(mag, 1e-30))[:, None]
                    velocity += (jt - c[ids, 4:7]) * w[:, None]
                    self.v[ids] = velocity
                    c[ids, 1] = jn
                    c[ids, 4:7] = jt
            if self.plane_axis >= 0:
                self.v[:, self.plane_axis] = 0
            displacement = np.linalg.norm(self.x - old, axis=1)
            max_errors = np.maximum(
                max_errors, np.abs(np.linalg.norm(np.diff(self.x, axis=0), axis=1) / self.rest - 1)
            )
            st["max_displacement"] = max(st["max_displacement"], float(displacement.max()))
            st["motion_violations"] += int(
                (displacement > 0.25 * self.rest.min() * (1 + 1e-5)).sum()
            )
            for k, col in enumerate(colliders):
                gap, _ = self.geometry(self.x, col)
                st["min_gap"] = min(st["min_gap"], float(gap[self.free].min()))
                c = self.contacts[:, k]
                st["max_normal_impulse"] = max(st["max_normal_impulse"], float(c[:, 1].max()))
                st["max_tangent_impulse"] = max(
                    st["max_tangent_impulse"], float(np.linalg.norm(c[:, 4:7], axis=1).max())
                )
                st["friction_cone_violation"] = max(
                    st["friction_cone_violation"],
                    float((np.linalg.norm(c[:, 4:7], axis=1) - c[:, 3] * c[:, 1]).max()),
                )
                if col.type == 3:
                    st["chord_bound"] = max(
                        st["chord_bound"],
                        float(col.radius - np.sqrt(col.radius**2 - (self.rest.max() / 2) ** 2)),
                    )
        self.previous = target.copy()
        st.update(
            max_length_error=float(max_errors.max()),
            p99_length_error=float(np.quantile(max_errors, 0.99, method="lower")),
            contacts=int((self.contacts[:, :, 0] >= 0).any(axis=1).sum()),
            native_ms=(time.perf_counter() - start) * 1000,
            nonfinite=int(not (np.isfinite(self.x).all() and np.isfinite(self.v).all())),
        )
        return st
