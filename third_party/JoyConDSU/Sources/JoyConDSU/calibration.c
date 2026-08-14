#include "calibration.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

static const double GRAVITY_MS2 = 9.80665;
static const double MIN_DURATION_SECONDS = 1.50;
static const double MAX_DURATION_SECONDS = 5.00;
static const double MIN_EFFECTIVE_RATE_HZ = 100.0;
static const double MAX_GYRO_STDDEV_RAD_S = 0.035;
static const double MAX_SEGMENT_SHIFT_RAD_S = 0.018;
static const double MIN_ACCEL_MEAN_G = 0.82;
static const double MAX_ACCEL_MEAN_G = 1.18;
static const double MAX_ACCEL_STDDEV_G = 0.035;
static const double MAX_ACCEL_SEGMENT_SHIFT_G = 0.035;
static const double MIN_GYRO_NOISE_RAD_S = 0.000001;

typedef struct {
    double mean;
    double m2;
    size_t count;
} Stats;

static void stats_push(Stats *stats, double value)
{
    stats->count += 1;
    const double delta = value - stats->mean;
    stats->mean += delta / (double)stats->count;
    stats->m2 += delta * (value - stats->mean);
}

static double stats_stddev(const Stats *stats)
{
    return stats->count < 2
        ? 0.0
        : sqrt(stats->m2 / (double)(stats->count - 1));
}

static int compare_double(const void *left, const void *right)
{
    const double a = *(const double *)left;
    const double b = *(const double *)right;
    return (a > b) - (a < b);
}

static double trimmed_mean(double values[CALIBRATION_REQUIRED_SAMPLES])
{
    qsort(values, CALIBRATION_REQUIRED_SAMPLES, sizeof(values[0]), compare_double);
    const size_t trim = CALIBRATION_REQUIRED_SAMPLES / 10;
    double sum = 0.0;
    for (size_t i = trim; i < CALIBRATION_REQUIRED_SAMPLES - trim; ++i) {
        sum += values[i];
    }
    return sum / (double)(CALIBRATION_REQUIRED_SAMPLES - 2 * trim);
}

static double trimmed_stddev(const double source[CALIBRATION_REQUIRED_SAMPLES])
{
    double values[CALIBRATION_REQUIRED_SAMPLES];
    memcpy(values, source, sizeof(values));
    qsort(values, CALIBRATION_REQUIRED_SAMPLES, sizeof(values[0]), compare_double);
    const size_t trim = CALIBRATION_REQUIRED_SAMPLES / 10;
    Stats stats = {0};
    for (size_t i = trim; i < CALIBRATION_REQUIRED_SAMPLES - trim; ++i) {
        stats_push(&stats, values[i]);
    }
    return stats_stddev(&stats);
}

static bool finite_vec(DsuVec3 value)
{
    return isfinite(value.x) && isfinite(value.y) && isfinite(value.z);
}

static double accel_norm(const MotionSample *sample)
{
    return sqrt(
        (double)sample->accel_ms2.x * sample->accel_ms2.x
        + (double)sample->accel_ms2.y * sample->accel_ms2.y
        + (double)sample->accel_ms2.z * sample->accel_ms2.z
    ) / GRAVITY_MS2;
}

void calibration_reset(CalibrationCollector *collector)
{
    if (collector != NULL) {
        memset(collector, 0, sizeof(*collector));
    }
}

CalibrationStatus calibration_push(
    CalibrationCollector *collector,
    const MotionSample *sample
)
{
    if (collector == NULL || sample == NULL
        || collector->count >= CALIBRATION_REQUIRED_SAMPLES) {
        return CALIBRATION_INVALID_ARGUMENT;
    }
    if (sample->timestamp_ns == 0
        || !finite_vec(sample->gyro_rad_s)
        || !finite_vec(sample->accel_ms2)) {
        return CALIBRATION_NONFINITE;
    }
    if (sample->timestamp_ns <= collector->last_timestamp_ns) {
        return CALIBRATION_DUPLICATE_TIMESTAMP;
    }

    collector->samples[collector->count++] = *sample;
    collector->last_timestamp_ns = sample->timestamp_ns;
    return collector->count == CALIBRATION_REQUIRED_SAMPLES
        ? CALIBRATION_VALID
        : CALIBRATION_PENDING;
}

CalibrationResult calibration_evaluate(const CalibrationCollector *collector)
{
    CalibrationResult result = {.status = CALIBRATION_INVALID_ARGUMENT};
    if (collector == NULL || collector->count != CALIBRATION_REQUIRED_SAMPLES) {
        return result;
    }

    double axes[3][CALIBRATION_REQUIRED_SAMPLES];
    Stats accel_stats = {0};
    double first_half_gyro[3] = {0};
    double second_half_gyro[3] = {0};
    double first_half_accel = 0.0;
    double second_half_accel = 0.0;

    for (size_t i = 0; i < CALIBRATION_REQUIRED_SAMPLES; ++i) {
        const MotionSample *sample = &collector->samples[i];
        if (!finite_vec(sample->gyro_rad_s) || !finite_vec(sample->accel_ms2)) {
            result.status = CALIBRATION_NONFINITE;
            return result;
        }

        const double gyro[3] = {
            sample->gyro_rad_s.x,
            sample->gyro_rad_s.y,
            sample->gyro_rad_s.z,
        };
        const double accel = accel_norm(sample);
        stats_push(&accel_stats, accel);

        for (size_t axis = 0; axis < 3; ++axis) {
            axes[axis][i] = gyro[axis];
            if (i < CALIBRATION_REQUIRED_SAMPLES / 2) {
                first_half_gyro[axis] += gyro[axis];
            } else {
                second_half_gyro[axis] += gyro[axis];
            }
        }
        if (i < CALIBRATION_REQUIRED_SAMPLES / 2) {
            first_half_accel += accel;
        } else {
            second_half_accel += accel;
        }
    }

    const uint64_t elapsed_ns =
        collector->samples[CALIBRATION_REQUIRED_SAMPLES - 1].timestamp_ns
        - collector->samples[0].timestamp_ns;
    result.duration_seconds = (double)elapsed_ns / 1000000000.0;
    result.effective_rate_hz = result.duration_seconds > 0.0
        ? (double)(CALIBRATION_REQUIRED_SAMPLES - 1) / result.duration_seconds
        : 0.0;
    if (result.duration_seconds < MIN_DURATION_SECONDS
        || result.duration_seconds > MAX_DURATION_SECONDS
        || result.effective_rate_hz < MIN_EFFECTIVE_RATE_HZ) {
        result.status = CALIBRATION_TIMING_UNSTABLE;
        return result;
    }

    result.accel_mean_g = accel_stats.mean;
    result.accel_stddev_g = stats_stddev(&accel_stats);
    if (result.accel_mean_g < MIN_ACCEL_MEAN_G
        || result.accel_mean_g > MAX_ACCEL_MEAN_G
        || result.accel_stddev_g > MAX_ACCEL_STDDEV_G) {
        result.status = CALIBRATION_ACCEL_INVALID;
        return result;
    }

    const double half = (double)(CALIBRATION_REQUIRED_SAMPLES / 2);
    if (fabs(first_half_accel / half - second_half_accel / half)
        > MAX_ACCEL_SEGMENT_SHIFT_G) {
        result.status = CALIBRATION_MOTION_DETECTED;
        return result;
    }

    double total_gyro_noise = 0.0;
    double robust_deviation[3] = {0};
    for (size_t axis = 0; axis < 3; ++axis) {
        const double deviation = trimmed_stddev(axes[axis]);
        robust_deviation[axis] = deviation;
        total_gyro_noise += deviation;
        if (deviation > MAX_GYRO_STDDEV_RAD_S
            || fabs(first_half_gyro[axis] / half - second_half_gyro[axis] / half)
                > MAX_SEGMENT_SHIFT_RAD_S) {
            result.status = CALIBRATION_MOTION_DETECTED;
            return result;
        }
    }
    if (total_gyro_noise < MIN_GYRO_NOISE_RAD_S) {
        result.status = CALIBRATION_FROZEN_STREAM;
        return result;
    }

    result.gyro_bias_rad_s = (DsuVec3){
        (float)trimmed_mean(axes[0]),
        (float)trimmed_mean(axes[1]),
        (float)trimmed_mean(axes[2]),
    };
    result.gyro_stddev_rad_s = (DsuVec3){
        (float)robust_deviation[0],
        (float)robust_deviation[1],
        (float)robust_deviation[2],
    };
    result.status = CALIBRATION_VALID;
    return result;
}

const char *calibration_status_message(CalibrationStatus status)
{
    switch (status) {
        case CALIBRATION_VALID: return "calibration valide";
        case CALIBRATION_NONFINITE: return "mesure non numérique";
        case CALIBRATION_DUPLICATE_TIMESTAMP: return "horodatage répété";
        case CALIBRATION_TIMING_UNSTABLE: return "cadence capteur instable";
        case CALIBRATION_ACCEL_INVALID: return "gravité ou accéléromètre incohérent";
        case CALIBRATION_MOTION_DETECTED: return "mouvement détecté";
        case CALIBRATION_FROZEN_STREAM: return "flux capteur figé";
        case CALIBRATION_PENDING: return "collecte en cours";
        default: return "calibration incomplète";
    }
}