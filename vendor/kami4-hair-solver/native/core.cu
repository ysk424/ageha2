#include "segment_geometry.cuh"
#include "api.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <cuda_runtime.h>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>
using Clock = std::chrono::steady_clock;
static thread_local std::string error;
#define HD __host__ __device__
struct V {
    float x, y, z;
    HD V(float a = 0, float b = 0, float c = 0) : x(a), y(b), z(c) {}
    HD float &operator[](int i) {
        return (&x)[i];
    }
    HD float operator[](int i) const {
        return (&x)[i];
    }
};
HD V operator+(V a, V b) {
    return {a.x + b.x, a.y + b.y, a.z + b.z};
}
HD V operator-(V a, V b) {
    return {a.x - b.x, a.y - b.y, a.z - b.z};
}
HD V operator*(V a, float t) {
    return {a.x * t, a.y * t, a.z * t};
}
HD V operator/(V a, float t) {
    return a * (1 / t);
}
HD V operator-(V a) {
    return a * (-1);
}
HD float dot(V a, V b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}
HD float norm(V a) {
    return sqrtf(dot(a, a));
}
HD V unit(V a) {
    return a / fmaxf(norm(a), 1e-20f);
}
HD V cross(V a, V b) {
    return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x};
}
HD V mix(V a, V b, float t) {
    return a * (1 - t) + b * t;
}
HD V xyz(const float *p) {
    return {p[0], p[1], p[2]};
}
HD V rotate(const float *q, V v) {
    V u(q[1], q[2], q[3]);
    return v + cross(u, v) * (2 * q[0]) + cross(u, cross(u, v)) * 2;
}
HD V inverse_rotate(const float *q, V v) {
    float inv[4] = {q[0], -q[1], -q[2], -q[3]};
    return rotate(inv, v);
}
HD K4Collider interpolate(K4Collider a, K4Collider b, float t) {
    K4Collider c = a;
    c.radius = a.radius * (1 - t) + b.radius * t;
    c.half_length = a.half_length * (1 - t) + b.half_length * t;
    for (int i = 0; i < 3; i++)
        c.center[i] = a.center[i] * (1 - t) + b.center[i] * t;
    float s = 0, d = 0;
    for (int i = 0; i < 4; i++)
        d += a.rotation[i] * b.rotation[i];
    for (int i = 0; i < 4; i++) {
        c.rotation[i] = (1 - t) * a.rotation[i] + t * b.rotation[i] * (d < 0 ? -1 : 1);
        s += c.rotation[i] * c.rotation[i];
    }
    for (int i = 0; i < 4; i++)
        c.rotation[i] /= sqrtf(s);
    return c;
}
struct Hit {
    float gap;
    V n, point, velocity;
    int id;
};
HD Hit analytic(V x, K4Collider c, float r) {
    V local = inverse_rotate(c.rotation, x - xyz(c.center)), q = local;
    float len, gap;
    V n;
    if (c.type == 0) {
        gap = local.z - r;
        n = {0, 0, 1};
        q.z = 0;
    } else {
        if (c.type == 2)
            q.z -= fminf(c.half_length, fmaxf(-c.half_length, q.z));
        if (c.type == 3)
            q.z = 0;
        len = norm(q);
        n = len > 1e-15f ? q / len : V(1, 0, 0);
        gap = len - c.radius - r;
        q = local - n * (len - c.radius);
    }
    return {gap, rotate(c.rotation, n), rotate(c.rotation, q) + xyz(c.center), {}, c.id};
}
struct Node {
    V lo, hi;
    int left, right, first, count, depth;
};
struct Tri {
    uint32_t a, b, c;
};
struct D {
    double x, y, z;
    HD D(double a = 0, double b = 0, double c = 0) : x(a), y(b), z(c) {}
    HD D(V v) : x(v.x), y(v.y), z(v.z) {}
    HD operator V() const {
        return V((float)x, (float)y, (float)z);
    }
};
HD D operator+(D a, D b) {
    return {a.x + b.x, a.y + b.y, a.z + b.z};
}
HD D operator-(D a, D b) {
    return {a.x - b.x, a.y - b.y, a.z - b.z};
}
HD D operator*(D a, double t) {
    return {a.x * t, a.y * t, a.z * t};
}
HD D operator/(D a, double t) {
    return a * (1 / t);
}
HD V minv(V a, V b) {
    return {fminf(a.x, b.x), fminf(a.y, b.y), fminf(a.z, b.z)};
}
HD V maxv(V a, V b) {
    return {fmaxf(a.x, b.x), fmaxf(a.y, b.y), fmaxf(a.z, b.z)};
}
HD float box_distance(V p, V lo, V hi) {
    V q = maxv(lo - p, maxv(p - hi, V()));
    return dot(q, q);
}
// Ericson's closest-point Voronoi regions, retaining barycentrics for surface velocity.
HD V closest(V p, V a, V b, V c, V &bary) {
    V ab = b - a, ac = c - a, ap = p - a;
    float d1 = dot(ab, ap), d2 = dot(ac, ap);
    if (d1 <= 0 && d2 <= 0) {
        bary = {1, 0, 0};
        return a;
    }
    V bp = p - b;
    float d3 = dot(ab, bp), d4 = dot(ac, bp);
    if (d3 >= 0 && d4 <= d3) {
        bary = {0, 1, 0};
        return b;
    }
    float vc = d1 * d4 - d3 * d2;
    if (vc <= 0 && d1 >= 0 && d3 <= 0) {
        float v = d1 / (d1 - d3);
        bary = {1 - v, v, 0};
        return a + ab * v;
    }
    V cp = p - c;
    float d5 = dot(ab, cp), d6 = dot(ac, cp);
    if (d6 >= 0 && d5 <= d6) {
        bary = {0, 0, 1};
        return c;
    }
    float vb = d5 * d2 - d1 * d6;
    if (vb <= 0 && d2 >= 0 && d6 <= 0) {
        float w = d2 / (d2 - d6);
        bary = {1 - w, 0, w};
        return a + ac * w;
    }
    float va = d3 * d6 - d5 * d4;
    if (va <= 0 && (d4 - d3) >= 0 && (d5 - d6) >= 0) {
        float w = (d4 - d3) / ((d4 - d3) + (d5 - d6));
        bary = {0, 1 - w, w};
        return b + (c - b) * w;
    }
    float den = 1 / fmaxf(va + vb + vc, 1e-30f);
    float v = vb * den, w = vc * den;
    bary = {1 - v - w, v, w};
    return a + ab * v + ac * w;
}
struct Contact {
    int id;
    float jn, support, mu;
    V jt, n, velocity;
};
struct PointDiag {
    float len, gap, disp, jn, jt, cone;
    uint32_t contact, motion, bad, overflow;
};
struct Device {
    int n, s, slots, nc, nv, nt, nn;
    K4Config cfg;
    int short_count, long_count, long_counts[3];
    int *short_ids, *long_ids;
    float min_length;
    V *x, *v, *old, *target0, *target1, *tmp, *dir, *mesh0, *mesh1, *mesh;
    D *rhs, *solution;
    float *mass, *w, *rest, *td, *to, *tr;
    double *b0, *b1, *b2, *l0, *l1, *l2;
    uint32_t *offsets;
    uint8_t *fixed;
    K4Collider *col0, *col1;
    Contact *contacts;
    PointDiag *diag;
    Node *nodes;
    Tri *tris;
    int *order;
    int animation_frames;
    int *animation_frame;
    V *animation_targets, *animation_mesh;
    V *mesh_previous;
    int mesh_contact_mode, extension_length_iterations;
    uint8_t *contact_enabled;
    V *fk_correction;
    uint32_t *fk_diag;
};
__device__ Hit mesh_hit(Device d, V x, int &overflow) {
    Hit h{d.cfg.contact_tolerance, {}, {}, {}, -1};
    if (!d.nt)
        return h;
    float radius = d.cfg.radius + d.cfg.contact_tolerance;
    float best = radius * radius;
    int stack[64], top = 0;
    stack[top++] = 0;
    V bary;
    while (top) {
        int ni = stack[--top];
        Node node = d.nodes[ni];
        if (box_distance(x, node.lo, node.hi) > best)
            continue;
        if (node.count) {
            for (int k = 0; k < node.count; k++) {
                int id = d.order[node.first + k];
                Tri t = d.tris[id];
                V a = d.mesh[t.a], b = d.mesh[t.b], c = d.mesh[t.c], bar;
                V q = closest(x, a, b, c, bar);
                float dist = dot(x - q, x - q);
                if (dist < best) {
                    best = dist;
                    h.id = id;
                    h.point = q;
                    V fn = unit(cross(b - a, c - a));
                    h.n = dist > 1e-20f ? (x - q) / sqrtf(dist) : fn;
                    h.gap = sqrtf(dist) - d.cfg.radius;
                    h.velocity = ((d.mesh1[t.a] - d.mesh0[t.a]) * bar.x +
                                  (d.mesh1[t.b] - d.mesh0[t.b]) * bar.y +
                                  (d.mesh1[t.c] - d.mesh0[t.c]) * bar.z) /
                                 d.cfg.dt;
                }
            }
        } else {
            if (top + 2 > 64) {
                overflow = 1;
                break;
            }
            float a = box_distance(x, d.nodes[node.left].lo, d.nodes[node.left].hi),
                  b = box_distance(x, d.nodes[node.right].lo, d.nodes[node.right].hi);
            if (a < b) {
                stack[top++] = node.right;
                stack[top++] = node.left;
            } else {
                stack[top++] = node.left;
                stack[top++] = node.right;
            }
        }
    }
    return h;
}
__global__ void blend_mesh(Device d, float t) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < d.nv) {
        d.mesh[i] = mix(d.mesh0[i], d.mesh1[i], t);
        d.mesh_previous[i] = mix(d.mesh0[i], d.mesh1[i], t - 1.0f / d.cfg.substeps);
    }
}
__global__ void refit(Device d, int depth) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= d.nn)
        return;
    Node n = d.nodes[i];
    if (n.depth != depth)
        return;
    V lo(1e30f, 1e30f, 1e30f), hi(-1e30f, -1e30f, -1e30f);
    if (n.count) {
        for (int k = 0; k < n.count; k++) {
            Tri t = d.tris[d.order[n.first + k]];
            lo = minv(lo, minv(d.mesh[t.a], minv(d.mesh[t.b], d.mesh[t.c])));
            hi = maxv(hi, maxv(d.mesh[t.a], maxv(d.mesh[t.b], d.mesh[t.c])));
            if (d.mesh_contact_mode) {
                lo = minv(lo, minv(d.mesh_previous[t.a], minv(d.mesh_previous[t.b], d.mesh_previous[t.c])));
                hi = maxv(hi, maxv(d.mesh_previous[t.a], maxv(d.mesh_previous[t.b], d.mesh_previous[t.c])));
            }
        }
    } else {
        lo = minv(d.nodes[n.left].lo, d.nodes[n.right].lo);
        hi = maxv(d.nodes[n.left].hi, d.nodes[n.right].hi);
    }
    d.nodes[i].lo = lo;
    d.nodes[i].hi = hi;
}
__global__ void begin_frame(Device d) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < d.n) {
        d.diag[i] = {};
        d.diag[i].gap = 1e20f;
    }
    if (i < d.s) for (int k = 0; k < 6; ++k) d.fk_diag[6*i+k] = 0;
}
__global__ void load_animation(Device d) {
    if (!d.animation_frames)
        return;
    int frame = *d.animation_frame;
    if (frame < 0)
        return;
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < d.n)
        d.target1[i] = d.animation_targets[(size_t)frame * d.n + i];
    if (i < d.nv) {
        d.mesh0[i] = d.animation_mesh[(size_t)(frame > 0 ? frame - 1 : 0) * d.nv + i];
        d.mesh1[i] = d.animation_mesh[(size_t)frame * d.nv + i];
    }
}
__global__ void bend(Device d, float t) {
    int s = blockIdx.x * blockDim.x + threadIdx.x;
    if (s >= d.short_count)
        return;
    s = d.short_ids[s];
    int a = d.offsets[s], b = d.offsets[s + 1];
    double h = (double)d.cfg.dt / d.cfg.substeps, decay = exp(-(double)d.cfg.damping * h);
    D g = xyz(d.cfg.gravity), origin = d.x[a];
    for (int i = a; i < b; i++) {
        d.old[i] = d.x[i];
        d.tmp[i] = mix(d.target0[i], d.target1[i], t);
        d.rhs[i] = d.fixed[i] ? (D(d.tmp[i]) - origin)
                              : (D(d.x[i]) - origin + D(d.v[i]) * (h * decay) + g * (h * h)) *
                                    (double)d.mass[i];
        for (int c = 0; c < d.slots; c++)
            d.contacts[i * d.slots + c].support = 0;
    }
    for (int i = a; i < b; i++) {
        if (d.fixed[i])
            continue;
        D r = d.rhs[i];
        if (i > a && d.fixed[i - 1])
            r = r - (D(d.tmp[i - 1]) - origin) * d.b1[i];
        if (i > a + 1 && d.fixed[i - 2])
            r = r - (D(d.tmp[i - 2]) - origin) * d.b2[i];
        if (i + 1 < b && d.fixed[i + 1])
            r = r - (D(d.tmp[i + 1]) - origin) * d.b1[i + 1];
        if (i + 2 < b && d.fixed[i + 2])
            r = r - (D(d.tmp[i + 2]) - origin) * d.b2[i + 2];
        d.rhs[i] = r;
    }
    for (int i = a; i < b; i++) {
        D r = d.rhs[i];
        if (i > a)
            r = r - d.rhs[i - 1] * d.l1[i];
        if (i > a + 1)
            r = r - d.rhs[i - 2] * d.l2[i];
        d.rhs[i] = r / d.l0[i];
    }
    for (int i = b - 1; i >= a; i--) {
        D r = d.rhs[i];
        if (i + 1 < b)
            r = r - d.solution[i + 1] * d.l1[i + 1];
        if (i + 2 < b)
            r = r - d.solution[i + 2] * d.l2[i + 2];
        d.solution[i] = r / d.l0[i];
    }
    for (int i = a; i < b; i++)
        d.x[i] = d.solution[i] + origin;
}
__global__ void length_solve(Device d) {
    int s = blockIdx.x * blockDim.x + threadIdx.x;
    if (s >= d.short_count)
        return;
    s = d.short_ids[s];
    int a = d.offsets[s], b = d.offsets[s + 1];
    int iterations = d.contact_enabled && !d.contact_enabled[b - 1] ? d.extension_length_iterations : 1;
    for (int iteration = 0; iteration < iterations; ++iteration) {
    for (int i = a; i < b - 1; i++) {
        V delta = d.x[i + 1] - d.x[i];
        float len = norm(delta), w = d.w[i] + d.w[i + 1];
        d.dir[i] = delta / fmaxf(len, 1e-20f);
        d.td[i] = w * (1 + d.cfg.regularization);
        d.tr[i] = d.rest[i] - len;
        d.to[i] = i > a ? -d.w[i] * dot(d.dir[i - 1], d.dir[i]) : 0;
        if (w == 0) {
            d.td[i] = 1;
            d.tr[i] = 0;
            d.to[i] = 0;
        }
    }
    for (int i = a + 1; i < b - 1; i++) {
        float f = d.to[i] / fmaxf(d.td[i - 1], 1e-20f);
        d.td[i] -= f * d.to[i];
        d.tr[i] -= f * d.tr[i - 1];
    }
    for (int i = b - 2; i >= a; i--) {
        float r = d.tr[i];
        if (i < b - 2)
            r -= d.to[i + 1] * d.tr[i + 1];
        d.tr[i] = r / fmaxf(d.td[i], 1e-20f);
    }
    for (int i = a; i < b; i++) {
        V delta;
        if (i > a)
            delta = delta + d.dir[i - 1] * d.tr[i - 1];
        if (i < b - 1)
            delta = delta - d.dir[i] * d.tr[i];
        d.x[i] = d.x[i] + delta * d.w[i];
    }
    }
}
// Parallel affine prefix solves the bandwidth-two triangular recurrence.
// Every lane participates; long strands never serialize substitution on lane zero.
struct Affine {
    double a, b, c, d;
    D u, v;
};
__device__ Affine compose(Affine x, Affine y) {
    return {x.a * y.a + x.b * y.c, x.a * y.b + x.b * y.d,       x.c * y.a + x.d * y.c,
            x.c * y.b + x.d * y.d, x.u + y.u * x.a + y.v * x.b, x.v + y.u * x.c + y.v * x.d};
}
__device__ D prefix_solve(Affine input, Affine *shared, int n) {
    int j = threadIdx.x, bank = 0;
    shared[j] = input;
    __syncthreads();
    for (int stride = 1; stride < n; stride *= 2) {
        Affine value = shared[bank * blockDim.x + j];
        if (j >= stride)
            value = compose(value, shared[bank * blockDim.x + j - stride]);
        shared[(1 - bank) * blockDim.x + j] = value;
        __syncthreads();
        bank = 1 - bank;
    }
    D out = shared[bank * blockDim.x + j].u;
    __syncthreads();
    return out;
}
__global__ void bend_long(Device d, float t, int offset) {
    extern __shared__ __align__(16) unsigned char raw[];
    auto shared = reinterpret_cast<Affine *>(raw);
    int s = d.long_ids[blockIdx.x + offset], a = d.offsets[s], b = d.offsets[s + 1],
        j = threadIdx.x, i = a + j, n = b - a;
    double h = (double)d.cfg.dt / d.cfg.substeps;
    D rhs, origin = d.x[a];
    if (j < n) {
        d.old[i] = d.x[i];
        d.tmp[i] = mix(d.target0[i], d.target1[i], t);
        for (int c = 0; c < d.slots; c++)
            d.contacts[i * d.slots + c].support = 0;
    }
    __syncthreads();
    if (j < n) {
        rhs = d.fixed[i] ? (D(d.tmp[i]) - origin)
                         : (D(d.x[i]) - origin + D(d.v[i]) * (h * exp(-(double)d.cfg.damping * h)) +
                            D(xyz(d.cfg.gravity)) * (h * h)) *
                               (double)d.mass[i];
        if (!d.fixed[i]) {
            if (i > a && d.fixed[i - 1])
                rhs = rhs - (D(d.tmp[i - 1]) - origin) * d.b1[i];
            if (i > a + 1 && d.fixed[i - 2])
                rhs = rhs - (D(d.tmp[i - 2]) - origin) * d.b2[i];
            if (i + 1 < b && d.fixed[i + 1])
                rhs = rhs - (D(d.tmp[i + 1]) - origin) * d.b1[i + 1];
            if (i + 2 < b && d.fixed[i + 2])
                rhs = rhs - (D(d.tmp[i + 2]) - origin) * d.b2[i + 2];
        }
    }
    Affine in{};
    if (j < n)
        in = {j ? -d.l1[i] / d.l0[i] : 0, j > 1 ? -d.l2[i] / d.l0[i] : 0, 1, 0, rhs / d.l0[i], {}};
    D y = prefix_solve(in, shared, n);
    if (j < n)
        d.rhs[i] = y;
    __syncthreads();
    i = b - 1 - j;
    in = {};
    if (j < n)
        in = {j ? -d.l1[i + 1] / d.l0[i] : 0,
              j > 1 ? -d.l2[i + 2] / d.l0[i] : 0,
              1,
              0,
              d.rhs[i] / d.l0[i],
              {}};
    D x = prefix_solve(in, shared, n);
    if (j < n)
        d.x[i] = x + origin;
}
// Parallel cyclic reduction: fixed ceil(log2(edge_count)) stages per topology bucket.
__global__ void length_long(Device d, int offset) {
    __shared__ float aa[2][256], bb[2][256], cc[2][256], rr[2][256];
    int s = d.long_ids[blockIdx.x + offset], a = d.offsets[s], b = d.offsets[s + 1],
        j = threadIdx.x, i = a + j, n = b - a - 1;
    int iterations = d.contact_enabled && !d.contact_enabled[b - 1] ? d.extension_length_iterations : 1;
    for (int iteration = 0; iteration < iterations; ++iteration) {
    if (j < n) {
        V delta = d.x[i + 1] - d.x[i];
        d.dir[i] = unit(delta);
        rr[0][j] = d.rest[i] - norm(delta);
        bb[0][j] = (d.w[i] + d.w[i + 1]) * (1 + d.cfg.regularization);
        if (d.w[i] + d.w[i + 1] == 0) {
            bb[0][j] = 1;
            rr[0][j] = 0;
        }
    }
    __syncthreads();
    if (j < n) {
        aa[0][j] = j ? -d.w[i] * dot(d.dir[i - 1], d.dir[i]) : 0;
        cc[0][j] = j + 1 < n ? -d.w[i + 1] * dot(d.dir[i + 1], d.dir[i]) : 0;
    }
    __syncthreads();
    int bank = 0;
    for (int stride = 1; stride < n; stride *= 2) {
        if (j < n) {
            float av = aa[bank][j], bv = bb[bank][j], cv = cc[bank][j], rv = rr[bank][j], an = 0,
                  cn = 0;
            if (j >= stride) {
                float f = av / fmaxf(bb[bank][j - stride], 1e-20f);
                bv -= f * cc[bank][j - stride];
                rv -= f * rr[bank][j - stride];
                an = -f * aa[bank][j - stride];
            }
            if (j + stride < n) {
                float f = cv / fmaxf(bb[bank][j + stride], 1e-20f);
                bv -= f * aa[bank][j + stride];
                rv -= f * rr[bank][j + stride];
                cn = -f * cc[bank][j + stride];
            }
            aa[1 - bank][j] = an;
            bb[1 - bank][j] = bv;
            cc[1 - bank][j] = cn;
            rr[1 - bank][j] = rv;
        }
        __syncthreads();
        bank = 1 - bank;
    }
    if (j < n)
        d.tr[i] = rr[bank][j] / fmaxf(bb[bank][j], 1e-20f);
    __syncthreads();
    if (j <= n) {
        V delta;
        if (j)
            delta = delta + d.dir[i - 1] * d.tr[i - 1];
        if (j < n)
            delta = delta - d.dir[i] * d.tr[i];
        d.x[i] = d.x[i] + delta * d.w[i];
    }
    __syncthreads();
    }
}
__global__ void project(Device d, float t) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= d.n || d.fixed[i] || (d.contact_enabled && !d.contact_enabled[i]))
        return;
    V x = d.x[i];
    float h = d.cfg.dt / d.cfg.substeps;
    for (int c = 0; c < d.slots; c++) {
        if (c >= d.nc && c != d.slots - 1)
            continue;
        if (c == d.slots - 1 && !d.nt)
            continue;
        Hit hit;
        float mu = d.cfg.friction;
        if (c == d.slots - 1) {
            int over = 0;
            hit = mesh_hit(d, x, over);
            d.diag[i].overflow |= over;
        } else {
            K4Collider col = interpolate(d.col0[c], d.col1[c], t);
            hit = analytic(x, col, d.cfg.radius);
            V local = inverse_rotate(col.rotation, hit.point - xyz(col.center));
            hit.velocity = (rotate(d.col1[c].rotation, local) + xyz(d.col1[c].center) -
                            rotate(d.col0[c].rotation, local) - xyz(d.col0[c].center)) /
                           d.cfg.dt;
            mu = col.friction;
        }
        Contact &con = d.contacts[i * d.slots + c];
        if (hit.gap <= d.cfg.contact_tolerance) {
            if (con.id != hit.id) {
                con.jn = 0;
                con.jt = {};
                con.id = hit.id;
            }
            con.n = hit.n;
            con.velocity = hit.velocity;
            con.mu = mu;
            if (hit.gap < 0) {
                float delta = -hit.gap;
                x = x + hit.n * delta;
                con.support += delta / (h * d.w[i]);
            }
        } else {
            con.id = -1;
            con.jn = 0;
            con.jt = {};
            con.support = 0;
        }
    }
    if (d.cfg.plane_axis >= 0)
        x[d.cfg.plane_axis] = d.cfg.plane_coordinate;
    d.x[i] = x;
}
#include "segment_contact.inl"
#include "local_fk_contact.inl"
__global__ void reconstruct(Device d) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= d.n)
        return;
    float h = d.cfg.dt / d.cfg.substeps;
    V v = (d.x[i] - d.old[i]) / h;
    if (d.mesh_contact_mode == 2 && d.nt) v = v - d.fk_correction[i] / h;
    if (!d.fixed[i])
        for (int c = 0; c < d.slots; c++) {
            Contact &con = d.contacts[i * d.slots + c];
            if (con.id < 0)
                continue;
            con.jt = con.jt - con.n * dot(con.jt, con.n);
            float cap = con.mu * con.jn;
            float mag = norm(con.jt);
            if (mag > cap)
                con.jt = con.jt * (cap / mag);
            v = v + (con.n * (con.jn - con.support) + con.jt) * d.w[i];
        }
    if (d.cfg.plane_axis >= 0)
        v[d.cfg.plane_axis] = 0;
    d.v[i] = v;
}
__global__ void impulse(Device d) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= d.n || d.fixed[i] || (d.contact_enabled && !d.contact_enabled[i]))
        return;
    V v = d.v[i];
    float w = d.w[i];
    for (int c = 0; c < d.slots; c++) {
        Contact &con = d.contacts[i * d.slots + c];
        if (con.id < 0)
            continue;
        V rel = v - con.velocity;
        float jn = fmaxf(0, con.jn - dot(rel, con.n) / w);
        v = v + con.n * ((jn - con.jn) * w);
        con.jn = jn;
        rel = v - con.velocity;
        V jt = con.jt - (rel - con.n * dot(rel, con.n)) / w;
        float mag = norm(jt), cap = con.mu * jn;
        if (mag > cap)
            jt = jt * (cap / mag);
        v = v + (jt - con.jt) * w;
        con.jt = jt;
    }
    if (d.cfg.plane_axis >= 0)
        v[d.cfg.plane_axis] = 0;
    d.v[i] = v;
}
__global__ void diagnostics(Device d, float t) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= d.n)
        return;
    PointDiag &st = d.diag[i];
    float disp = norm(d.x[i] - d.old[i]);
    st.disp = fmaxf(st.disp, disp);
    float l = d.rest[i];
    if (l > 0 && i + 1 < d.n) {
        float e = fabsf(norm(d.x[i + 1] - d.x[i]) / l - 1);
        st.len = fmaxf(st.len, e);
    } else
        l = 1e20f;
    float minl = d.min_length;
    if (i > 0 && d.rest[i - 1] > 0)
        minl = fminf(minl, d.rest[i - 1]);
    for (int c = 0; c < d.nc; c++)
        if (d.col0[c].type != 0)
            minl = fminf(minl, d.col0[c].radius);
    st.motion += (disp > .25f * minl * (1 + 1e-5f));
    st.bad |= !(isfinite(d.x[i].x) && isfinite(d.x[i].y) && isfinite(d.x[i].z) &&
                isfinite(d.v[i].x) && isfinite(d.v[i].y) && isfinite(d.v[i].z));
    if (d.fixed[i] || (d.contact_enabled && !d.contact_enabled[i]))
        return;
    for (int c = 0; c < d.slots; c++) {
        Contact con = d.contacts[i * d.slots + c];
        if (con.id >= 0) {
            st.contact = 1;
            st.jn = fmaxf(st.jn, con.jn);
            st.jt = fmaxf(st.jt, norm(con.jt));
            st.cone = fmaxf(st.cone, norm(con.jt) - con.mu * con.jn);
        }
        if (c < d.nc)
            st.gap = fminf(
                st.gap, analytic(d.x[i], interpolate(d.col0[c], d.col1[c], t), d.cfg.radius).gap);
    }
    if (d.nt) {
        int over = 0;
        st.gap = fminf(st.gap, mesh_hit(d, d.x[i], over).gap);
        st.overflow |= over;
    }
}
struct Handle {
    Device d{};
    std::vector<void *> allocations;
    std::vector<PointDiag> stats;
    std::vector<float> errors;
    std::vector<uint32_t> offsets;
    int depth = 0;
    float maxedge = 0;
    cudaEvent_t start{}, end{};
    cudaStream_t stream{};
    cudaGraph_t graph{};
    cudaGraphExec_t graph_exec{};
    int kernel_launches = 0;
    bool resident_call = false;
    int next_animation_frame = 0;
};
static void ck(cudaError_t e) {
    if (e != cudaSuccess)
        throw std::runtime_error(cudaGetErrorString(e));
}
template <class T> static T *alloc(Handle &h, size_t n) {
    if (!n)
        return nullptr;
    T *p;
    ck(cudaMalloc(&p, n * sizeof(T)));
    h.allocations.push_back(p);
    ck(cudaMemset(p, 0, n * sizeof(T)));
    return p;
}
template <class T> static void upload(T *d, const T *s, size_t n) {
    if (n)
        ck(cudaMemcpy(d, s, n * sizeof(T), cudaMemcpyHostToDevice));
}
static double ms(Clock::time_point a, Clock::time_point b) {
    return std::chrono::duration<double, std::milli>(b - a).count();
}
static int build_node(std::vector<Node> &nodes, std::vector<int> &ids, const std::vector<V> &cent,
                      const std::vector<V> &verts, const std::vector<Tri> &tri, int a, int b,
                      int dep, int &maxdepth) {
    int index = (int)nodes.size();
    nodes.push_back({});
    maxdepth = std::max(dep, maxdepth);
    Node node{};
    node.first = a;
    node.depth = dep;
    node.lo = {1e30f, 1e30f, 1e30f};
    node.hi = {-1e30f, -1e30f, -1e30f};
    for (int i = a; i < b; i++) {
        Tri t = tri[ids[i]];
        node.lo = minv(node.lo, minv(verts[t.a], minv(verts[t.b], verts[t.c])));
        node.hi = maxv(node.hi, maxv(verts[t.a], maxv(verts[t.b], verts[t.c])));
    }
    if (b - a <= 4)
        node.count = b - a;
    else {
        V e = node.hi - node.lo;
        int axis = e.y > e.x ? 1 : 0;
        if (e.z > e[axis])
            axis = 2;
        int mid = (a + b) / 2;
        std::nth_element(ids.begin() + a, ids.begin() + mid, ids.begin() + b,
                         [&](int i, int j) { return cent[i][axis] < cent[j][axis]; });
        node.left = build_node(nodes, ids, cent, verts, tri, a, mid, dep + 1, maxdepth);
        node.right = build_node(nodes, ids, cent, verts, tri, mid, b, dep + 1, maxdepth);
    }
    nodes[index] = node;
    return index;
}
K4_API const char *k4_error() {
    return error.c_str();
}
K4_API const char *k4_version() {
    return "K4-FK 0.3.0 CUDA sm_120 ABI1";
}
K4_API void k4_destroy(void *ptr) {
    if (!ptr)
        return;
    Handle *h = (Handle *)ptr;
    if (h->graph_exec)
        cudaGraphExecDestroy(h->graph_exec);
    if (h->graph)
        cudaGraphDestroy(h->graph);
    if (h->stream)
        cudaStreamDestroy(h->stream);
    for (void *p : h->allocations)
        cudaFree(p);
    if (h->start)
        cudaEventDestroy(h->start);
    if (h->end)
        cudaEventDestroy(h->end);
    delete h;
}
K4_API int k4_create(const K4Config *cfg, int n, int s, const float *positions,
                     const uint32_t *offsets, const uint8_t *fixed, int capacity, void **result) {
    Handle *h = nullptr;
    try {
        error.clear();
        if (!result)
            throw std::runtime_error("Null output handle");
        *result = nullptr;
        if (!cfg || !positions || !offsets || !fixed || n < 2 || s < 1 || capacity < 0 ||
            capacity > 32)
            throw std::runtime_error("Invalid input pointers/counts");
        for (int j = 0; j < 11; j++)
            if (!std::isfinite(((const float *)cfg)[j]))
                throw std::runtime_error("Nonfinite configuration");
        if (!std::isfinite(cfg->plane_coordinate) || cfg->contact_tolerance < 0)
            throw std::runtime_error("Invalid tolerance/plane");
        for (int i = 0; i < n; i++)
            if (fixed[i] > 1)
                throw std::runtime_error("Kinematic mask must be zero or one");
        if (!(cfg->dt > 0 && cfg->density > 0 && cfg->bending >= 0 && cfg->radius > 0 &&
              cfg->damping >= 0 && cfg->friction >= 0 && cfg->regularization > 0))
            throw std::runtime_error("Invalid material");
        if ((cfg->substeps != 2 && cfg->substeps != 4 && cfg->substeps != 8) || cfg->passes < 2 ||
            cfg->passes > 32 || cfg->impulses < 2 || cfg->impulses > 4)
            throw std::runtime_error("Budget must be substeps 2/4/8, P 2..32 and I 2..4");
        if (cfg->plane_axis < -1 || cfg->plane_axis > 2)
            throw std::runtime_error("Invalid plane axis");
        for (int k = 0; k < s; k++)
            if (offsets[k + 1] <= offsets[k] || offsets[k + 1] > (uint32_t)n ||
                offsets[k + 1] - offsets[k] < 2 || offsets[k + 1] - offsets[k] > 256)
                throw std::runtime_error("Invalid strand offsets");
        if (offsets[0] != 0 || offsets[s] != (uint32_t)n)
            throw std::runtime_error("Offsets do not cover points");
        h = new Handle;
        Device &d = h->d;
        d.n = n;
        d.s = s;
        d.slots = capacity + 1;
        d.cfg = *cfg;
        h->offsets.assign(offsets, offsets + s + 1);
        h->stats.resize(n);
        h->errors.resize(n - s);
        d.min_length = 1e20f;
        std::vector<int> shorts, longs, buckets[6];
        for (int k = 0; k < s; k++) {
            int count = offsets[k + 1] - offsets[k], bucket = 0;
            while (bucket < 5 && count > (8 << bucket))
                bucket++;
            buckets[bucket].push_back(k);
        }
        for (int k = 0; k < 6; k++) {
            auto &dst = k < 3 ? shorts : longs;
            dst.insert(dst.end(), buckets[k].begin(), buckets[k].end());
            if (k >= 3)
                d.long_counts[k - 3] = (int)buckets[k].size();
        }
        d.short_count = (int)shorts.size();
        d.long_count = (int)longs.size();
        d.short_ids = alloc<int>(*h, shorts.size());
        d.long_ids = alloc<int>(*h, longs.size());
        upload(d.short_ids, shorts.data(), shorts.size());
        upload(d.long_ids, longs.data(), longs.size());
        d.x = alloc<V>(*h, n);
        d.v = alloc<V>(*h, n);
        d.old = alloc<V>(*h, n);
        d.target0 = alloc<V>(*h, n);
        d.target1 = alloc<V>(*h, n);
        d.rhs = alloc<D>(*h, n);
        d.solution = alloc<D>(*h, n);
        d.tmp = alloc<V>(*h, n);
        d.dir = alloc<V>(*h, n);
        d.mass = alloc<float>(*h, n);
        d.w = alloc<float>(*h, n);
        d.rest = alloc<float>(*h, n);
        d.b0 = alloc<double>(*h, n);
        d.b1 = alloc<double>(*h, n);
        d.b2 = alloc<double>(*h, n);
        d.l0 = alloc<double>(*h, n);
        d.l1 = alloc<double>(*h, n);
        d.l2 = alloc<double>(*h, n);
        d.td = alloc<float>(*h, n);
        d.to = alloc<float>(*h, n);
        d.tr = alloc<float>(*h, n);
        d.offsets = alloc<uint32_t>(*h, s + 1);
        d.fixed = alloc<uint8_t>(*h, n);
        d.col0 = alloc<K4Collider>(*h, capacity);
        d.col1 = alloc<K4Collider>(*h, capacity);
        d.contacts = alloc<Contact>(*h, n * d.slots);
        d.diag = alloc<PointDiag>(*h, n);
        d.fk_correction = alloc<V>(*h, n);
        d.fk_diag = alloc<uint32_t>(*h, s * 6);
        std::vector<float> mass(n), w(n), rest(n);
        std::vector<double> b0(n), b1(n), b2(n), l0(n), l1(n), l2(n);
        const V *x = (const V *)positions;
        double dt = cfg->dt / cfg->substeps;
        for (int k = 0; k < s; k++) {
            int a = offsets[k], b = offsets[k + 1];
            if (b - a < 2 || b - a > 256)
                throw std::runtime_error("Strands require 2..256 points; no strand is dropped");
            for (int i = a; i < b - 1; i++) {
                rest[i] = norm(x[i + 1] - x[i]);
                if (!(rest[i] > 1e-8f) || !std::isfinite(rest[i]))
                    throw std::runtime_error("Zero/invalid edge: normalize before create");
                h->maxedge = std::max(h->maxedge, rest[i]);
                d.min_length = std::min(d.min_length, rest[i]);
                mass[i] += .5f * cfg->density * rest[i];
                mass[i + 1] += .5f * cfg->density * rest[i];
            }
            std::vector<double> a0(b - a), a1(b - a), a2(b - a), f0(b - a), f1(b - a), f2(b - a);
            for (int i = a; i < b; i++) {
                a0[i - a] = mass[i];
                w[i] = fixed[i] ? 0 : 1 / mass[i];
            }
            for (int i = a + 1; i < b - 1; i++) {
                double l = rest[i - 1], r = rest[i], avg = (l + r) * .5,
                       q[3] = {1 / (avg * l), -(1 / l + 1 / r) / avg, 1 / (avg * r)},
                       coef = dt * dt * cfg->bending * avg;
                for (int j = 0; j < 3; j++)
                    for (int m = 0; m <= j; m++) {
                        int row = i - 1 + j - a;
                        double v = coef * q[j] * q[m];
                        if (j == m)
                            a0[row] += v;
                        else if (j - m == 1)
                            a1[row] += v;
                        else
                            a2[row] += v;
                    }
            }
            for (int i = a; i < b; i++) {
                int j = i - a;
                b0[i] = a0[j];
                b1[i] = a1[j];
                b2[i] = a2[j];
                if (fixed[i])
                    a0[j] = 1;
                if (j && (fixed[i] || fixed[i - 1]))
                    a1[j] = 0;
                if (j > 1 && (fixed[i] || fixed[i - 2]))
                    a2[j] = 0;
            }
            for (int j = 0; j < b - a; j++) {
                f2[j] = j > 1 ? a2[j] / f0[j - 2] : 0;
                f1[j] = j ? (a1[j] - f2[j] * f1[j - 1]) / f0[j - 1] : 0;
                double diag = a0[j] - f1[j] * f1[j] - f2[j] * f2[j];
                if (!(diag > 0))
                    throw std::runtime_error("Bending matrix not positive definite");
                f0[j] = std::sqrt(diag);
                l0[a + j] = f0[j];
                l1[a + j] = f1[j];
                l2[a + j] = f2[j];
            }
        }
        upload(d.x, x, n);
        upload(d.target0, x, n);
        upload(d.target1, x, n);
        upload(d.offsets, offsets, s + 1);
        upload(d.fixed, fixed, n);
        upload(d.mass, mass.data(), n);
        upload(d.w, w.data(), n);
        upload(d.rest, rest.data(), n);
        upload(d.b0, b0.data(), n);
        upload(d.b1, b1.data(), n);
        upload(d.b2, b2.data(), n);
        upload(d.l0, l0.data(), n);
        upload(d.l1, l1.data(), n);
        upload(d.l2, l2.data(), n);
        std::vector<Contact> contacts(n * d.slots);
        for (auto &c : contacts)
            c.id = -1;
        upload(d.contacts, contacts.data(), contacts.size());
        ck(cudaEventCreate(&h->start));
        ck(cudaEventCreate(&h->end));
        *result = h;
        return 0;
    } catch (const std::exception &e) {
        error = e.what();
        k4_destroy(h);
        return 1;
    }
}
K4_API int k4_set_mesh(void *ptr, int nv, const float *positions, int nt,
                       const uint32_t *triangles) {
    try {
        if (!ptr || nv < 3 || nt < 1 || !positions || !triangles)
            throw std::runtime_error("Invalid mesh");
        Handle &h = *(Handle *)ptr;
        Device &d = h.d;
        if (d.nt || h.graph_exec)
            throw std::runtime_error("Mesh topology is immutable; reinitialize");
        std::vector<V> verts((const V *)positions, (const V *)positions + nv);
        std::vector<Tri> tris((const Tri *)triangles, (const Tri *)triangles + nt);
        std::vector<int> ids(nt);
        std::iota(ids.begin(), ids.end(), 0);
        std::vector<V> cent(nt);
        for (int i = 0; i < nt; i++) {
            Tri t = tris[i];
            if (t.a >= nv || t.b >= nv || t.c >= nv)
                throw std::runtime_error("Triangle index out of range");
            cent[i] = (verts[t.a] + verts[t.b] + verts[t.c]) / 3;
        }
        std::vector<Node> nodes;
        nodes.reserve(nt);
        build_node(nodes, ids, cent, verts, tris, 0, nt, 0, h.depth);
        d.nv = nv;
        d.nt = nt;
        d.nn = (int)nodes.size();
        d.mesh0 = alloc<V>(h, nv);
        d.mesh1 = alloc<V>(h, nv);
        d.mesh = alloc<V>(h, nv);
        d.mesh_previous = alloc<V>(h, nv);
        d.tris = alloc<Tri>(h, nt);
        d.order = alloc<int>(h, nt);
        d.nodes = alloc<Node>(h, nodes.size());
        upload(d.mesh0, verts.data(), nv);
        upload(d.mesh1, verts.data(), nv);
        upload(d.mesh, verts.data(), nv);
        upload(d.mesh_previous, verts.data(), nv);
        upload(d.tris, tris.data(), nt);
        upload(d.order, ids.data(), nt);
        upload(d.nodes, nodes.data(), nodes.size());
        return 0;
    } catch (const std::exception &e) {
        error = e.what();
        return 1;
    }
}
static int launch_fixed_frame(Handle &h) {
    Device d = h.d;
    int blocks = (d.n + 127) / 128, sb = (d.short_count + 63) / 64, launches = 1;
    if (d.animation_frames) {
        load_animation<<<(std::max(d.n, d.nv) + 127) / 128, 128, 0, h.stream>>>(d);
        launches++;
    }
    begin_frame<<<blocks, 128, 0, h.stream>>>(d);
    for (int sub = 0; sub < d.cfg.substeps; sub++) {
        float t = float(sub + 1) / d.cfg.substeps;
        if (d.nt) {
            blend_mesh<<<(d.nv + 127) / 128, 128, 0, h.stream>>>(d, t);
            launches++;
            for (int dep = h.depth; dep >= 0; dep--) {
                refit<<<(d.nn + 127) / 128, 128, 0, h.stream>>>(d, dep);
                launches++;
            }
        }
        if (d.short_count) {
            bend<<<sb, 64, 0, h.stream>>>(d, t);
            launches++;
        }
        for (int k = 0, offset = 0; k < 3; offset += d.long_counts[k++])
            if (d.long_counts[k]) {
                int threads = 64 << k;
                bend_long<<<d.long_counts[k], threads, 2 * threads * sizeof(Affine), h.stream>>>(
                    d, t, offset);
                launches++;
            }
        for (int p = 0; p < d.cfg.passes; p++) {
            if (d.short_count) {
                length_solve<<<sb, 64, 0, h.stream>>>(d);
                launches++;
            }
            for (int k = 0, offset = 0; k < 3; offset += d.long_counts[k++])
                if (d.long_counts[k]) {
                    length_long<<<d.long_counts[k], 64 << k, 0, h.stream>>>(d, offset);
                    launches++;
                }
            project<<<blocks, 128, 0, h.stream>>>(d, t);
            launches++;
            if (d.nt && d.mesh_contact_mode) {
                if (p == 0) {
                    project_segments<true><<<blocks, 128, 0, h.stream>>>(d, 0);
                    project_segments<true><<<blocks, 128, 0, h.stream>>>(d, 1);
                } else {
                    project_segments<false><<<blocks, 128, 0, h.stream>>>(d, 0);
                    project_segments<false><<<blocks, 128, 0, h.stream>>>(d, 1);
                }
                launches += 2;
            }
        }
        project<<<blocks, 128, 0, h.stream>>>(d, t);
        if (d.nt && d.mesh_contact_mode) {
            project_segments<false><<<blocks, 128, 0, h.stream>>>(d, 0);
            project_segments<false><<<blocks, 128, 0, h.stream>>>(d, 1);
            launches += 2;
        }
        if (d.nt && d.mesh_contact_mode == 2) {
            repair_local_fk<<<(d.s + 63) / 64, 64, 0, h.stream>>>(d);
            launches++;
        }
        reconstruct<<<blocks, 128, 0, h.stream>>>(d);
        launches += 2;
        for (int j = 0; j < d.cfg.impulses; j++) {
            impulse<<<blocks, 128, 0, h.stream>>>(d);
            launches++;
        }
        diagnostics<<<blocks, 128, 0, h.stream>>>(d, t);
        launches++;
    }
    return launches;
}
K4_API int k4_prepare(void *ptr, int nc) {
    try {
        if (!ptr)
            throw std::runtime_error("Null prepare handle");
        Handle &h = *(Handle *)ptr;
        if (nc < 0 || nc >= h.d.slots)
            throw std::runtime_error("Prepare collider capacity exceeded");
        if (h.graph_exec) {
            if (nc != h.d.nc)
                throw std::runtime_error("Collider count changed; reinitialize");
            return 0;
        }
        h.d.nc = nc;
        ck(cudaStreamCreateWithFlags(&h.stream, cudaStreamNonBlocking));
        ck(cudaStreamBeginCapture(h.stream, cudaStreamCaptureModeGlobal));
        h.kernel_launches = launch_fixed_frame(h);
        ck(cudaStreamEndCapture(h.stream, &h.graph));
        ck(cudaGraphInstantiate(&h.graph_exec, h.graph, nullptr, nullptr, 0));
        return 0;
    } catch (const std::exception &e) {
        error = e.what();
        return 7;
    }
}
K4_API int k4_step(void *ptr, const float *target, const K4Collider *col0, const K4Collider *col1,
                   int nc, const float *mesh0, const float *mesh1, K4Stats *out) {
    try {
        if (!ptr || !out)
            throw std::runtime_error("Null step pointer");
        Handle &h = *(Handle *)ptr;
        Device &d = h.d;
        if (!target && !(h.resident_call && d.animation_frames))
            throw std::runtime_error("Missing targets");
        if (nc < 0 || nc >= d.slots || (nc && (!col0 || !col1)))
            throw std::runtime_error("Collider capacity exceeded");
        for (int c = 0; c < nc; c++) {
            if (col0[c].id != col1[c].id || col0[c].type != col1[c].type || col0[c].type < 0 ||
                col0[c].type > 3)
                throw std::runtime_error("Collider ID/type changed");
            for (auto *p : {&col0[c], &col1[c]}) {
                for (int j = 0; j < 10; j++)
                    if (!std::isfinite(((const float *)p->center)[j]))
                        throw std::runtime_error("Nonfinite collider");
                float q = 0;
                for (float v : p->rotation)
                    q += v * v;
                if (fabsf(q - 1) > 1e-3f || p->friction < 0 || p->radius <= 0 || p->half_length < 0)
                    throw std::runtime_error("Invalid collider geometry");
            }
        }
        if (!h.graph_exec || d.nc != nc)
            throw std::runtime_error(
                "Call k4_prepare after topology setup; collider count is immutable");
        auto t0 = Clock::now();
        if (!h.resident_call) {
            if (d.animation_frames) {
                int inactive = -1;
                upload(d.animation_frame, &inactive, 1);
            }
            upload(d.target1, (const V *)target, d.n);
        }
        upload(d.col0, col0, nc);
        upload(d.col1, col1, nc);
        if (d.nt && !h.resident_call) {
            if (!mesh0 || !mesh1)
                throw std::runtime_error("Mesh animation missing");
            upload(d.mesh0, (const V *)mesh0, d.nv);
            upload(d.mesh1, (const V *)mesh1, d.nv);
        }
        // Uploads use the legacy stream; the captured graph uses a nonblocking stream.
        // Establish an explicit dependency before the graph reads its input buffers.
        ck(cudaStreamSynchronize(nullptr));
        auto t1 = Clock::now();
        ck(cudaEventRecord(h.start, h.stream));
        int launches = h.kernel_launches;
        ck(cudaGraphLaunch(h.graph_exec, h.stream));
        ck(cudaGetLastError());
        ck(cudaEventRecord(h.end, h.stream));
        ck(cudaEventSynchronize(h.end));
        float elapsed;
        ck(cudaEventElapsedTime(&elapsed, h.start, h.end));
        auto t2 = Clock::now();
        ck(cudaMemcpy(h.stats.data(), d.diag, d.n * sizeof(PointDiag), cudaMemcpyDeviceToHost));
        ck(cudaMemcpy(d.target0, d.target1, d.n * sizeof(V), cudaMemcpyDeviceToDevice));
        auto t3 = Clock::now();
        *out = {};
        out->native_ms = elapsed;
        out->upload_ms = ms(t0, t1);
        out->download_ms = ms(t2, t3);
        out->points = d.n;
        out->strands = d.s;
        out->launches = launches;
        out->min_gap = 1e20f;
        size_t ei = 0;
        int strand = 0;
        for (int i = 0; i < d.n; i++) {
            auto &s = h.stats[i];
            if (i == (int)h.offsets[strand + 1] - 1)
                strand++;
            else
                h.errors[ei++] = s.len;
            out->max_length_error = std::max(out->max_length_error, s.len);
            out->min_gap = std::min(out->min_gap, s.gap);
            out->max_displacement = std::max(out->max_displacement, s.disp);
            out->max_normal_impulse = std::max(out->max_normal_impulse, s.jn);
            out->max_tangent_impulse = std::max(out->max_tangent_impulse, s.jt);
            out->friction_cone_violation = std::max(out->friction_cone_violation, s.cone);
            out->contacts += s.contact;
            out->motion_violations += s.motion;
            out->nonfinite += s.bad;
            out->overflow += s.overflow;
        }
        size_t p99 = size_t(.99 * (h.errors.size() - 1));
        std::nth_element(h.errors.begin(), h.errors.begin() + p99, h.errors.end());
        out->p99_length_error = h.errors[p99];
        for (int c = 0; c < nc; c++)
            if (col0[c].type == 3) {
                float r = col0[c].radius, l = h.maxedge;
                out->chord_bound = std::max(out->chord_bound,
                                            l <= 2 * r ? r - std::sqrt(r * r - .25f * l * l) : r);
            }
        if (out->nonfinite || out->overflow)
            throw std::runtime_error(out->nonfinite ? "Nonfinite GPU state" : "BVH stack overflow");
        return 0;
    } catch (const std::exception &e) {
        error = e.what();
        return 2;
    }
}
K4_API int k4_download(void *ptr, float *x, float *v) {
    try {
        if (!ptr || !x)
            throw std::runtime_error("Invalid download");
        Device &d = ((Handle *)ptr)->d;
        ck(cudaMemcpy(x, d.x, d.n * sizeof(V), cudaMemcpyDeviceToHost));
        if (v)
            ck(cudaMemcpy(v, d.v, d.n * sizeof(V), cudaMemcpyDeviceToHost));
        return 0;
    } catch (const std::exception &e) {
        error = e.what();
        return 3;
    }
}
K4_API int k4_set_state(void *ptr, const float *x, const float *v) {
    try {
        if (!ptr || !x || !v)
            throw std::runtime_error("Invalid state");
        Device &d = ((Handle *)ptr)->d;
        upload(d.x, (const V *)x, d.n);
        upload(d.v, (const V *)v, d.n);
        upload(d.target0, (const V *)x, d.n);
        upload(d.target1, (const V *)x, d.n);
        return 0;
    } catch (const std::exception &e) {
        error = e.what();
        return 4;
    }
}
K4_API int k4_contact_data(void *ptr, float *out) {
    try {
        if (!ptr || !out)
            throw std::runtime_error("Null contact download");
        Device &d = ((Handle *)ptr)->d;
        std::vector<Contact> data(d.n * d.slots);
        ck(cudaMemcpy(data.data(), d.contacts, data.size() * sizeof(Contact),
                      cudaMemcpyDeviceToHost));
        for (size_t i = 0; i < data.size(); i++) {
            const Contact &c = data[i];
            float *q = out + i * 13;
            q[0] = (float)c.id;
            q[1] = c.jn;
            q[2] = c.support;
            q[3] = c.mu;
            q[4] = c.jt.x;
            q[5] = c.jt.y;
            q[6] = c.jt.z;
            q[7] = c.n.x;
            q[8] = c.n.y;
            q[9] = c.n.z;
            q[10] = c.velocity.x;
            q[11] = c.velocity.y;
            q[12] = c.velocity.z;
        }
        return 0;
    } catch (const std::exception &e) {
        error = e.what();
        return 5;
    }
}
K4_API int k4_point_data(void *ptr, float *out) {
    if (!ptr || !out) {
        error = "Null diagnostic output";
        return 5;
    }
    Handle &h = *(Handle *)ptr;
    for (int i = 0; i < h.d.n; i++) {
        auto &s = h.stats[i];
        float *q = out + 8 * i;
        q[0] = s.len;
        q[1] = s.gap;
        q[2] = s.disp;
        q[3] = (float)s.motion;
        q[4] = (float)s.contact;
        q[5] = s.jn;
        q[6] = s.jt;
        q[7] = s.cone;
    }
    return 0;
}
K4_API int k4_probe(void *ptr, int mode, const float *target, const K4Collider *cols, int nc) {
    try {
        if (!ptr)
            throw std::runtime_error("Null probe");
        Handle &h = *(Handle *)ptr;
        Device &d = h.d;
        if (nc < 0 || nc >= d.slots)
            throw std::runtime_error("Probe collider capacity");
        d.nc = nc;
        upload(d.col0, cols, nc);
        upload(d.col1, cols, nc);
        if (target)
            upload(d.target1, (const V *)target, d.n);
        int b = (d.n + 127) / 128, s = (d.short_count + 63) / 64;
        if (mode == 0) {
            if (d.short_count)
                bend<<<s, 64>>>(d, 1);
            for (int k = 0, offset = 0; k < 3; offset += d.long_counts[k++])
                if (d.long_counts[k]) {
                    int threads = 64 << k;
                    bend_long<<<d.long_counts[k], threads, 2 * threads * sizeof(Affine)>>>(d, 1,
                                                                                           offset);
                }
        } else if (mode == 1) {
            if (d.short_count)
                length_solve<<<s, 64>>>(d);
            for (int k = 0, offset = 0; k < 3; offset += d.long_counts[k++])
                if (d.long_counts[k])
                    length_long<<<d.long_counts[k], 64 << k>>>(d, offset);
        } else if (mode == 2)
            project<<<b, 128>>>(d, 1);
        else if (mode == 3) {
            reconstruct<<<b, 128>>>(d);
            impulse<<<b, 128>>>(d);
        } else if (mode == 5) {
            begin_frame<<<b, 128>>>(d);
            repair_local_fk<<<(d.s + 63) / 64, 64>>>(d);
        } else if (mode == 4)
            impulse<<<b, 128>>>(d);
        else
            throw std::runtime_error("Unknown probe mode");
        ck(cudaGetLastError());
        ck(cudaDeviceSynchronize());
        return 0;
    } catch (const std::exception &e) {
        error = e.what();
        return 6;
    }
}
K4_API int k4_set_animation(void *ptr, int frames, const float *targets, const float *vertices) {
    try {
        if (!ptr || frames < 1 || !targets) throw std::runtime_error("Invalid animation");
        Handle &h = *(Handle *)ptr;
        Device &d = h.d;
        if (h.graph_exec || d.animation_frames) throw std::runtime_error("Animation must be set once before prepare");
        if (d.nv && !vertices) throw std::runtime_error("Missing animated mesh");
        d.animation_frame = alloc<int>(h, 1);
        d.animation_targets = alloc<V>(h, (size_t)frames * d.n);
        d.animation_mesh = alloc<V>(h, (size_t)frames * d.nv);
        int inactive = -1;
        upload(d.animation_frame, &inactive, 1);
        upload(d.animation_targets, (const V *)targets, (size_t)frames * d.n);
        upload(d.animation_mesh, (const V *)vertices, (size_t)frames * d.nv);
        d.animation_frames = frames;
        h.next_animation_frame = 0;
        return 0;
    } catch (const std::exception &e) { error = e.what(); return 8; }
}
K4_API int k4_step_animation(void *ptr, int frame, K4Stats *out) {
    try {
        if (!ptr || !out) throw std::runtime_error("Null animation handle");
        Handle &h = *(Handle *)ptr;
        if (frame != h.next_animation_frame || frame < 0 || frame >= h.d.animation_frames)
            throw std::runtime_error("Animation frames must be sequential");
        if (!h.graph_exec || h.d.nc != 0) throw std::runtime_error("Prepare mesh-only animation first");
        auto began = Clock::now();
        upload(h.d.animation_frame, &frame, 1);
        double upload_ms = ms(began, Clock::now());
        h.resident_call = true;
        int result = k4_step(ptr, nullptr, nullptr, nullptr, 0, nullptr, nullptr, out);
        h.resident_call = false;
        if (!result) { h.next_animation_frame++; out->upload_ms += upload_ms; }
        return result;
    } catch (const std::exception &e) { error = e.what(); return 9; }
}
K4_API int k4_set_contact_options(void *ptr, int mode, const uint8_t *mask, int extension_iterations) {
    try {
        if (!ptr || mode < 0 || mode > 2 || !mask || extension_iterations < 1 || extension_iterations > 16) throw std::runtime_error("Invalid contact options");
        Handle &h = *(Handle *)ptr;
        if (h.graph_exec || h.d.contact_enabled) throw std::runtime_error("Set contact options once before prepare");
        h.d.contact_enabled = alloc<uint8_t>(h, h.d.n);
        upload(h.d.contact_enabled, mask, h.d.n);
        h.d.mesh_contact_mode = mode;
        h.d.extension_length_iterations = extension_iterations;
        return 0;
    } catch (const std::exception &e) { error = e.what(); return 10; }
}

K4_API int k4_fk_data(void *ptr, uint32_t *out) {
    try {
        if (!ptr || !out) throw std::runtime_error("Null FK diagnostic download");
        Device &d = ((Handle *)ptr)->d;
        ck(cudaMemcpy(out, d.fk_diag, d.s * 6 * sizeof(uint32_t), cudaMemcpyDeviceToHost));
        return 0;
    } catch (const std::exception &e) { error = e.what(); return 11; }
}
