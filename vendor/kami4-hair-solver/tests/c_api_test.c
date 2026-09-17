#include "api.h"
#include <assert.h>
#include <math.h>
#include <stddef.h>
#include <stdio.h>

int main(void) {
    K4Config config = {0};
    config.dt = 1.0f / 24;
    config.bending = 1e-6f;
    config.density = 1e-4f;
    config.radius = 4e-5f;
    config.damping = 8;
    config.friction = .35f;
    config.gravity[2] = -9.80665f;
    config.regularization = 1e-7f;
    config.contact_tolerance = .00015f;
    config.substeps = 4;
    config.passes = config.impulses = 3;
    config.plane_axis = -1;
    float input[6] = {0, 0, .1f, .01f, 0, .1f};
    float output[6], velocity[6];
    uint32_t offsets[2] = {0, 2};
    uint8_t fixed[2] = {1, 0};
    void *handle = NULL;
    K4Stats stats;
    assert(k4_create(&config, 2, 1, input, offsets, fixed, 0, &handle) == 0);
    assert(handle != NULL);
    assert(k4_step(handle, input, NULL, NULL, 0, NULL, NULL, &stats) != 0);
    assert(k4_prepare(handle, 0) == 0);
    for (int frame = 0; frame < 10; ++frame) {
        assert(k4_step(handle, input, NULL, NULL, 0, NULL, NULL, &stats) == 0);
        assert(stats.points == 2 && stats.strands == 1);
        assert(stats.nonfinite == 0 && stats.overflow == 0);
        assert(stats.frame_allocations == 0 && stats.launches == 53);
        assert(k4_download(handle, output, velocity) == 0);
        for (int i = 0; i < 6; ++i) {
            assert(isfinite(output[i]) && isfinite(velocity[i]));
        }
        for (int i = 0; i < 3; ++i)
            assert(output[i] == input[i]);
    }
    k4_destroy(handle);
    handle = NULL;
    config.substeps = 64;
    assert(k4_create(&config, 2, 1, input, offsets, fixed, 0, &handle) != 0);
    assert(handle == NULL);
    printf("C ABI and immutable CUDA graph budget verified: %s\n", k4_version());
    return 0;
}
