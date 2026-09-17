namespace sg = kami::cuda_geometry;
__device__ sg::DVec3 geo(V x) { return {x.x, x.y, x.z}; }
__device__ bool boxes_overlap(V al, V ah, V bl, V bh) {
    return al.x <= bh.x && ah.x >= bl.x && al.y <= bh.y && ah.y >= bl.y && al.z <= bh.z && ah.z >= bl.z;
}
__device__ bool segment_box(V p, V q, V lo, V hi, float radius) {
    float enter = 0, leave = 1;
    for (int axis = 0; axis < 3; ++axis) {
        float delta = q[axis] - p[axis];
        float a = lo[axis] - radius, b = hi[axis] + radius;
        if (fabsf(delta) < 1e-20f) {
            if (p[axis] < a || p[axis] > b) return false;
        } else {
            float t0 = (a - p[axis]) / delta, t1 = (b - p[axis]) / delta;
            enter = fmaxf(enter, fminf(t0, t1));
            leave = fminf(leave, fmaxf(t0, t1));
            if (enter > leave) return false;
        }
    }
    return true;
}
__device__ void mesh_support(Device d, int node, int id, V n, V velocity, V correction) {
    if (!d.w[node]) return;
    Contact &con = d.contacts[node * d.slots + d.slots - 1];
    if (con.id != id) { con.id = id; con.jn = 0; con.jt = {}; }
    con.n = n; con.velocity = velocity; con.mu = d.cfg.friction;
    con.support += fmaxf(0, dot(correction, n)) / ((d.cfg.dt / d.cfg.substeps) * d.w[node]);
}
// A conservative separating plane in a frame translating with triangle vertex a.
__device__ bool swept_separated(V p0, V p1, V q0, V q1, V a0, V b0, V c0, V a1, V b1, V c1, V n, float radius) {
    V shift = a1 - a0;
    float hair = fminf(fminf(dot(p0, n), dot(p1, n)), fminf(dot(q0 - shift, n), dot(q1 - shift, n)));
    float body = fmaxf(fmaxf(dot(a0, n), dot(b0, n)), dot(c0, n));
    body = fmaxf(body, fmaxf(fmaxf(dot(a1 - shift, n), dot(b1 - shift, n)), dot(c1 - shift, n)));
    return hair - body > radius;
}
template<bool ccd> __global__ void project_segments(Device d, int color) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i + 1 >= d.n || (i & 1) != color || d.rest[i] <= 0 || !d.mesh_contact_mode || !d.nt)
        return;
    if ((d.contact_enabled && (!d.contact_enabled[i] || !d.contact_enabled[i + 1])) || (d.fixed[i] && d.fixed[i + 1]))
        return;
    V p0 = d.x[i], p1 = d.x[i + 1];
    V old0 = ccd ? d.old[i] : p0, old1 = ccd ? d.old[i + 1] : p1;
    float sweep = fmaxf(norm(p0 - old0), norm(p1 - old1));
    float radius = d.cfg.radius + d.cfg.contact_tolerance;
    V margin{radius, radius, radius};
    V low = minv(minv(old0, old1), minv(p0, p1)) - margin;
    V high = maxv(maxv(old0, old1), maxv(p0, p1)) + margin;
    int stack[64], top = 0; stack[top++] = 0;
    while (top) {
        Node node = d.nodes[stack[--top]];
        if (!boxes_overlap(low, high, node.lo, node.hi)) continue;
        if (!segment_box(p0, p1, node.lo, node.hi, radius + sweep)) continue;
        if (!node.count) {
            if (top + 2 > 64) { d.diag[i].overflow = 1; break; }
            stack[top++] = node.left; stack[top++] = node.right;
            continue;
        }
        for (int k = 0; k < node.count; ++k) {
            if (!ccd) { old0 = p0; old1 = p1; }
            int id = d.order[node.first + k]; Tri tr = d.tris[id];
            V a1 = d.mesh[tr.a], b1 = d.mesh[tr.b], c1 = d.mesh[tr.c];
            V a0 = ccd ? d.mesh_previous[tr.a] : a1, b0 = ccd ? d.mesh_previous[tr.b] : b1, c0 = ccd ? d.mesh_previous[tr.c] : c1;
            V tl = minv(minv(a0, minv(b0, c0)), minv(a1, minv(b1, c1)));
            V th = maxv(maxv(a0, maxv(b0, c0)), maxv(a1, maxv(b1, c1)));
            if (!boxes_overlap(low, high, tl, th)) continue;
            if (!segment_box(p0, p1, tl, th, radius + sweep)) continue;
            auto pair = sg::closest_segment_triangle(geo(old0), geo(old1), geo(a0), geo(b0), geo(c0));
            double alpha = 0;
            if constexpr (ccd) {
            V initial_body = a0 * (float)pair.bary.x + b0 * (float)pair.bary.y + c0 * (float)pair.bary.z;
            V initial_hair = mix(old0, old1, (float)pair.t);
            V separating_normal = unit(initial_hair - initial_body);
            if (pair.distance > radius && swept_separated(old0, old1, p0, p1, a0, b0, c0, a1, b1, c1, separating_normal, radius))
                continue;
            V da = a1 - a0, db = b1 - b0, dc = c1 - c0;
            float speed = fmaxf(norm((p0 - old0) - da), norm((p1 - old1) - da)) + fmaxf(norm(db - da), norm(dc - da));
            bool candidate = false;
            for (int it = 0; it < 64; ++it) {
                if (pair.distance <= radius + 1e-7) { candidate = true; break; }
                if (speed <= 1e-12f) break;
                double advance = .9 * (pair.distance - radius) / speed;
                if (alpha + advance > 1) break;
                alpha += advance;
                pair = sg::closest_segment_triangle(geo(mix(old0, p0, (float)alpha)), geo(mix(old1, p1, (float)alpha)),
                    geo(mix(a0, a1, (float)alpha)), geo(mix(b0, b1, (float)alpha)), geo(mix(c0, c1, (float)alpha)));
                if (it == 63 || advance < 1e-7) { candidate = true; break; }
            }
            if (!candidate) {
                pair = sg::closest_segment_triangle(geo(p0), geo(p1), geo(a1), geo(b1), geo(c1));
                if (pair.distance > radius + 1e-7) continue;
                alpha = 1;
            }
            } else {
                if (pair.distance > radius + 1e-7) continue;
            }
            float u = (float)pair.t;
            V ac = mix(a0, a1, (float)alpha), bc = mix(b0, b1, (float)alpha), cc = mix(c0, c1, (float)alpha);
            V face_n = unit(cross(bc - ac, cc - ac));
            V at_hit = ac * (float)pair.bary.x + bc * (float)pair.bary.y + cc * (float)pair.bary.z;
            V hair_hit = mix(mix(old0, p0, (float)alpha), mix(old1, p1, (float)alpha), u);
            V n = pair.distance > 1e-8 ? unit(hair_hit - at_hit) : face_n;
            if (pair.distance <= 1e-8) {
                V pa = d.mesh_previous[tr.a], pb = d.mesh_previous[tr.b], pc = d.mesh_previous[tr.c];
                V previous_body = pa * (float)pair.bary.x + pb * (float)pair.bary.y + pc * (float)pair.bary.z;
                V previous_n = cross(pb-pa,pc-pa);
                if (dot(mix(d.old[i],d.old[i+1],u)-previous_body,previous_n) < 0) n = n * -1;
            }
            V endpoint = a1 * (float)pair.bary.x + b1 * (float)pair.bary.y + c1 * (float)pair.bary.z;
            float penetration = radius - dot(mix(p0, p1, u) - endpoint, n);
            float w0 = d.w[i] * (1 - u), w1 = d.w[i + 1] * u;
            float denominator = w0 * (1 - u) + w1 * u;
            if (penetration <= 0 || denominator < 1e-15f) continue;
            float lambda = penetration / denominator;
            V d0 = n * (lambda * w0), d1 = n * (lambda * w1);
            V velocity = ((d.mesh1[tr.a] - d.mesh0[tr.a]) * (float)pair.bary.x +
                (d.mesh1[tr.b] - d.mesh0[tr.b]) * (float)pair.bary.y +
                (d.mesh1[tr.c] - d.mesh0[tr.c]) * (float)pair.bary.z) / d.cfg.dt;
            p0 = p0 + d0; p1 = p1 + d1;
            mesh_support(d, i, id, n, velocity, d0);
            mesh_support(d, i + 1, id, n, velocity, d1);
        }
    }
    d.x[i] = p0; d.x[i + 1] = p1;
}
