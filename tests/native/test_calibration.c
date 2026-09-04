#include "calibration.h"

#include <assert.h>
#include <math.h>
#include <stddef.h>
#include <stdint.h>

static MotionSample sample_at(size_t index, DsuVec3 gyro, DsuVec3 accel)
{
    return (MotionSample){
        .gyro_rad_s = gyro,
        .accel_ms2 = accel,
        .timestamp_ns = 1000000000ULL + (uint64_t)index * 5000000ULL,
    };
}

static CalibrationResult stationary_calibration(bool with_outlier)
{
    CalibrationCollector collector;
    calibration_reset(&collector);
    for (size_t i = 0; i < CALIBRATION_REQUIRED_SAMPLES; ++i) {
        const float noise = (float)((int)(i % 7) - 3) * 0.00005f;
        DsuVec3 gyro = {0.010f + noise, -0.020f - noise, 0.030f + noise};
        if (with_outlier && i == 123) {
            gyro.x = 2.0f;
        }
        MotionSample sample = sample_at(
            i,
            gyro,
            (DsuVec3){noise, 9.80665f, -noise}
        );
        const CalibrationStatus status = calibration_push(&collector, &sample);
        assert(status == (i + 1 == CALIBRATION_REQUIRED_SAMPLES
            ? CALIBRATION_VALID : CALIBRATION_PENDING));
    }
    return calibration_evaluate(&collector);
}

int main(void)
{
    CalibrationResult stable = stationary_calibration(false);
    assert(stable.status == CALIBRATION_VALID);
    assert(stable.effective_rate_hz > 199.0 && stable.effective_rate_hz < 201.0);
    assert(fabs(stable.gyro_bias_rad_s.x - 0.010) < 0.0001);

    /* Une pointe isolée est écartée de la moyenne robuste. */
    CalibrationResult robust = stationary_calibration(true);
    assert(robust.status == CALIBRATION_VALID);
    assert(fabs(robust.gyro_bias_rad_s.x - 0.010) < 0.0001);

    /* Une rotation lente entre les deux moitiés doit être refusée. */
    CalibrationCollector moving;
    calibration_reset(&moving);
    for (size_t i = 0; i < CALIBRATION_REQUIRED_SAMPLES; ++i) {
        const float progress = (float)i / (float)CALIBRATION_REQUIRED_SAMPLES;
        MotionSample sample = sample_at(
            i,
            (DsuVec3){0.001f + 0.04f * progress, 0.0f, 0.0f},
            (DsuVec3){0.0f, 9.80665f, 0.0f}
        );
        (void)calibration_push(&moving, &sample);
    }
    assert(calibration_evaluate(&moving).status == CALIBRATION_MOTION_DETECTED);

    /* Un flux parfaitement figé n'est pas une preuve d'immobilité réelle. */
    CalibrationCollector frozen;
    calibration_reset(&frozen);
    for (size_t i = 0; i < CALIBRATION_REQUIRED_SAMPLES; ++i) {
        MotionSample sample = sample_at(
            i,
            (DsuVec3){0.0f, 0.0f, 0.0f},
            (DsuVec3){0.0f, 9.80665f, 0.0f}
        );
        (void)calibration_push(&frozen, &sample);
    }
    assert(calibration_evaluate(&frozen).status == CALIBRATION_FROZEN_STREAM);

    /* Doublons et valeurs non finies sont refusés dès la collecte. */
    CalibrationCollector invalid;
    calibration_reset(&invalid);
    MotionSample first = sample_at(
        0, (DsuVec3){0.0f, 0.0f, 0.0f}, (DsuVec3){0.0f, 9.8f, 0.0f}
    );
    assert(calibration_push(&invalid, &first) == CALIBRATION_PENDING);
    assert(calibration_push(&invalid, &first) == CALIBRATION_DUPLICATE_TIMESTAMP);
    MotionSample nan_sample = sample_at(
        1, (DsuVec3){NAN, 0.0f, 0.0f}, (DsuVec3){0.0f, 9.8f, 0.0f}
    );
    assert(calibration_push(&invalid, &nan_sample) == CALIBRATION_NONFINITE);

    /* Une cadence artificiellement trop rapide est détectée. */
    CalibrationCollector timing;
    calibration_reset(&timing);
    for (size_t i = 0; i < CALIBRATION_REQUIRED_SAMPLES; ++i) {
        MotionSample sample = sample_at(
            i,
            (DsuVec3){0.01f + (float)(i % 2) * 0.0001f, 0.0f, 0.0f},
            (DsuVec3){0.0f, 9.80665f, 0.0f}
        );
        sample.timestamp_ns = 1000000000ULL + (uint64_t)i * 1000000ULL;
        (void)calibration_push(&timing, &sample);
    }
    assert(calibration_evaluate(&timing).status == CALIBRATION_TIMING_UNSTABLE);

    return 0;
}
