#pragma once
#include <stdint.h>
#ifdef __cplusplus
#define K4_EXTERN extern "C"
#else
#define K4_EXTERN extern
#endif
#if defined(_WIN32) && defined(K4_BUILD_DLL)
#define K4_API K4_EXTERN __declspec(dllexport)
#elif defined(_WIN32)
#define K4_API K4_EXTERN __declspec(dllimport)
#else
#define K4_API K4_EXTERN
#endif
typedef struct K4Config {
    float dt, bending, density, radius, damping, friction, gravity[3], regularization,
        contact_tolerance;
    int substeps, passes, impulses;
    int plane_axis;
    float plane_coordinate;
} K4Config;
// type 0: plane (local Z normal), 1: sphere, 2: capsule, 3: infinite cylinder (local Z axis).
typedef struct K4Collider {
    int type, id;
    float center[3], rotation[4], radius, half_length, friction;
} K4Collider;
typedef struct K4Stats {
    double native_ms, upload_ms, download_ms;
    float max_length_error, p99_length_error, min_gap, chord_bound, max_displacement;
    float max_normal_impulse, max_tangent_impulse, friction_cone_violation;
    uint32_t points, strands, contacts, motion_violations, nonfinite, overflow, frame_allocations,
        launches;
} K4Stats;
K4_API int k4_create(const K4Config *, int, int, const float *, const uint32_t *, const uint8_t *,
                     int, void **);
K4_API int k4_set_mesh(void *, int, const float *, int, const uint32_t *);
K4_API int k4_step(void *, const float *, const K4Collider *, const K4Collider *, int,
                   const float *, const float *, K4Stats *);
K4_API int k4_download(void *, float *, float *);
K4_API int k4_set_state(void *, const float *, const float *);
// Diagnostics: 13 floats/contact: id, jn, support, mu, jt.xyz, n.xyz, collider_velocity.xyz.
K4_API int k4_contact_data(void *, float *);
K4_API int k4_point_data(void *, float *);
// Isolated production-kernel validation, outside the runtime frame path.
K4_API int k4_probe(void *, int, const float *, const K4Collider *, int);
K4_API void k4_destroy(void *);
K4_API const char *k4_error(void);
K4_API const char *k4_version(void);

K4_API int k4_prepare(void *, int);
// Upload immutable animation before prepare; frame indices are zero based and sequential.
K4_API int k4_set_animation(void *, int, const float *, const float *);
K4_API int k4_step_animation(void *, int, K4Stats *);
// mode 0: nodes; mode 1: visible segments; mode 2: segments + local FK repair.
K4_API int k4_set_contact_options(void *, int, const uint8_t *, int);
// Six uint32 per strand: queries, repairs, max rewind, unresolved, moved points, active.
K4_API int k4_fk_data(void *, uint32_t *);
