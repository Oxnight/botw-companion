#ifndef JOYCON_DSU_CALIBRATION_H
#define JOYCON_DSU_CALIBRATION_H

#include "motion_pipeline.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    CALIBRATION_REQUIRED_SAMPLES = 400,
};

typedef enum {
    CALIBRATION_PENDING = 0,
    CALIBRATION_VALID = 1,
    CALIBRATION_INVALID_ARGUMENT = 2,
    CALIBRATION_NONFINITE = 3,
    CALIBRATION_DUPLICATE_TIMESTAMP = 4,
    CALIBRATION_TIMING_UNSTABLE = 5,
    CALIBRATION_ACCEL_INVALID = 6,
    CALIBRATION_MOTION_DETECTED = 7,
    CALIBRATION_FROZEN_STREAM = 8,
} CalibrationStatus;

typedef struct {
    MotionSample samples[CALIBRATION_REQUIRED_SAMPLES];
    size_t count;
    uint64_t last_timestamp_ns;
} CalibrationCollector;

typedef struct {
    DsuVec3 gyro_bias_rad_s;
    DsuVec3 gyro_stddev_rad_s;
    double accel_mean_g;
    double accel_stddev_g;
    double duration_seconds;
    double effective_rate_hz;
    CalibrationStatus status;
} CalibrationResult;

void calibration_reset(CalibrationCollector *collector);
CalibrationStatus calibration_push(
    CalibrationCollector *collector,
    const MotionSample *sample
);
CalibrationResult calibration_evaluate(const CalibrationCollector *collector);
const char *calibration_status_message(CalibrationStatus status);

#ifdef __cplusplus
}
#endif

#endif
