#include "motion_pipeline.h"

#include <math.h>
#include <limits.h>
#include <string.h>

/* Une demi-période HID autour du flux Joy-Con nominal à 200 Hz. */
static const uint64_t MAX_PAIRING_DISTANCE_NS = 3000000ULL;
static const uint64_t EXPECTED_INTERVAL_NS = 5000000ULL;

static bool finite_vec(DsuVec3 value)
{
    return isfinite(value.x) && isfinite(value.y) && isfinite(value.z);
}

static uint64_t normalized_timestamp(
    MotionPipeline *pipeline,
    uint64_t sensor_timestamp_ns,
    uint64_t fallback_timestamp_ns
)
{
    if (sensor_timestamp_ns == 0) {
        return fallback_timestamp_ns;
    }

    if (pipeline->sensor_origin_ns == 0) {
        pipeline->sensor_origin_ns = sensor_timestamp_ns;
        pipeline->host_origin_ns = fallback_timestamp_ns;
    }

    if (sensor_timestamp_ns < pipeline->sensor_origin_ns) {
        return 0;
    }

    return pipeline->host_origin_ns
        + (sensor_timestamp_ns - pipeline->sensor_origin_ns);
}

static uint64_t timestamp_distance(uint64_t a, uint64_t b)
{
    return a >= b ? a - b : b - a;
}

void motion_pipeline_reset(MotionPipeline *pipeline)
{
    if (pipeline != NULL) {
        memset(pipeline, 0, sizeof(*pipeline));
    }
}

static const TimedMotionValue *find_matching_gyro(
    const MotionPipeline *pipeline,
    uint64_t accel_timestamp_ns
)
{
    const TimedMotionValue *closest = NULL;
    uint64_t closest_distance = UINT64_MAX;

    for (size_t i = 0; i < MOTION_HISTORY_SIZE; ++i) {
        const TimedMotionValue *candidate = &pipeline->gyro[i];
        if (!candidate->valid) {
            continue;
        }

        const uint64_t distance =
            timestamp_distance(candidate->timestamp_ns, accel_timestamp_ns);

        if (distance < closest_distance) {
            closest = candidate;
            closest_distance = distance;
        }
    }

    return closest_distance <= MAX_PAIRING_DISTANCE_NS ? closest : NULL;
}

static const TimedMotionValue *find_matching_accel(
    const MotionPipeline *pipeline,
    uint64_t gyro_timestamp_ns
)
{
    const TimedMotionValue *closest = NULL;
    uint64_t closest_distance = UINT64_MAX;

    for (size_t i = 0; i < MOTION_HISTORY_SIZE; ++i) {
        const TimedMotionValue *candidate = &pipeline->accel[i];
        if (!candidate->valid) {
            continue;
        }

        const uint64_t distance =
            timestamp_distance(candidate->timestamp_ns, gyro_timestamp_ns);
        if (distance < closest_distance) {
            closest = candidate;
            closest_distance = distance;
        }
    }

    return closest_distance <= MAX_PAIRING_DISTANCE_NS ? closest : NULL;
}

static bool emit_pair(
    MotionPipeline *pipeline,
    const TimedMotionValue *gyro,
    const TimedMotionValue *accel,
    MotionSample *sample
)
{
    if (gyro == NULL || accel == NULL) {
        return false;
    }

    const uint64_t timestamp_ns =
        gyro->timestamp_ns >= accel->timestamp_ns
            ? gyro->timestamp_ns
            : accel->timestamp_ns;
    if (timestamp_ns <= pipeline->last_emitted_timestamp_ns) {
        return false;
    }

    *sample = (MotionSample){
        .gyro_rad_s = gyro->value,
        .accel_ms2 = accel->value,
        .timestamp_ns = timestamp_ns,
        .received_timestamp_ns =
            gyro->received_timestamp_ns >= accel->received_timestamp_ns
                ? gyro->received_timestamp_ns
                : accel->received_timestamp_ns,
    };
    pipeline->last_emitted_timestamp_ns = timestamp_ns;
    pipeline->stats.emitted_samples += 1;
    /*
     * SDL peut livrer plusieurs échantillons dans une même rafale. Leur date
     * de réception est alors identique : ces intervalles nuls doivent compter
     * dans la moyenne, sinon trois mesures toutes les 15 ms seraient annoncées
     * à tort comme un flux à 66,7 Hz au lieu de 200 Hz.
     */
    const uint64_t received_ns = sample->received_timestamp_ns;
    if (pipeline->stats.last_received_ns != 0
        && received_ns >= pipeline->stats.last_received_ns) {
        const uint64_t interval = received_ns - pipeline->stats.last_received_ns;
        const uint64_t jitter = interval >= EXPECTED_INTERVAL_NS
            ? interval - EXPECTED_INTERVAL_NS
            : EXPECTED_INTERVAL_NS - interval;
        pipeline->stats.interval_count += 1;
        pipeline->stats.interval_sum_ns += (long double)interval;
        pipeline->stats.jitter_sum_ns += (long double)jitter;
        if (jitter > pipeline->stats.jitter_max_ns) {
            pipeline->stats.jitter_max_ns = jitter;
        }
    }
    pipeline->stats.last_received_ns = received_ns;
    return true;
}

bool motion_pipeline_push(
    MotionPipeline *pipeline,
    MotionSensorKind kind,
    DsuVec3 value,
    uint64_t sensor_timestamp_ns,
    uint64_t fallback_timestamp_ns,
    MotionSample *sample
)
{
    if (pipeline == NULL || sample == NULL) {
        return false;
    }
    pipeline->stats.sensor_events += 1;
    if (!finite_vec(value)) {
        pipeline->stats.invalid_values += 1;
        return false;
    }
    if (sensor_timestamp_ns == 0) {
        pipeline->stats.fallback_timestamps += 1;
    }

    const uint64_t timestamp_ns =
        normalized_timestamp(pipeline, sensor_timestamp_ns, fallback_timestamp_ns);
    if (timestamp_ns == 0) {
        pipeline->stats.regressive_timestamps += 1;
        return false;
    }

    if (kind == MOTION_SENSOR_GYRO) {
        if (timestamp_ns <= pipeline->last_gyro_timestamp_ns) {
            if (timestamp_ns == pipeline->last_gyro_timestamp_ns) {
                pipeline->stats.duplicate_timestamps += 1;
            } else {
                pipeline->stats.regressive_timestamps += 1;
            }
            return false;
        }

        TimedMotionValue *entry = &pipeline->gyro[pipeline->gyro_next];
        *entry = (TimedMotionValue){
            .value = value,
            .timestamp_ns = timestamp_ns,
            .received_timestamp_ns = fallback_timestamp_ns,
            .valid = true,
        };
        pipeline->gyro_next = (pipeline->gyro_next + 1) % MOTION_HISTORY_SIZE;
        pipeline->last_gyro_timestamp_ns = timestamp_ns;
        pipeline->latest_gyro_rad_s = value;
        pipeline->has_latest_gyro = true;
        pipeline->stats.accepted_gyro += 1;
        const bool emitted = emit_pair(
            pipeline,
            entry,
            find_matching_accel(pipeline, timestamp_ns),
            sample
        );
        pipeline->stats.pairing_waits += emitted ? 0u : 1u;
        return emitted;
    }

    if (kind != MOTION_SENSOR_ACCEL) {
        pipeline->stats.invalid_values += 1;
        return false;
    }
    if (timestamp_ns <= pipeline->last_accel_timestamp_ns) {
        if (timestamp_ns == pipeline->last_accel_timestamp_ns) {
            pipeline->stats.duplicate_timestamps += 1;
        } else {
            pipeline->stats.regressive_timestamps += 1;
        }
        return false;
    }

    pipeline->last_accel_timestamp_ns = timestamp_ns;
    TimedMotionValue *entry = &pipeline->accel[pipeline->accel_next];
    *entry = (TimedMotionValue){
        .value = value,
        .timestamp_ns = timestamp_ns,
        .received_timestamp_ns = fallback_timestamp_ns,
        .valid = true,
    };
    pipeline->accel_next = (pipeline->accel_next + 1) % MOTION_HISTORY_SIZE;
    pipeline->stats.accepted_accel += 1;
    const TimedMotionValue *gyro = find_matching_gyro(pipeline, timestamp_ns);
    const bool emitted = emit_pair(pipeline, gyro, entry, sample);
    pipeline->stats.pairing_waits += emitted ? 0u : 1u;
    return emitted;
}

bool motion_pipeline_latest_gyro(
    const MotionPipeline *pipeline,
    DsuVec3 *gyro_rad_s
)
{
    if (pipeline == NULL || gyro_rad_s == NULL || !pipeline->has_latest_gyro) {
        return false;
    }

    *gyro_rad_s = pipeline->latest_gyro_rad_s;
    return true;
}

const MotionPipelineStats *motion_pipeline_stats(const MotionPipeline *pipeline)
{
    return pipeline == NULL ? NULL : &pipeline->stats;
}

double motion_pipeline_received_hz(const MotionPipeline *pipeline)
{
    if (pipeline == NULL || pipeline->stats.interval_count == 0
        || pipeline->stats.interval_sum_ns <= 0.0L) {
        return 0.0;
    }
    const long double mean = pipeline->stats.interval_sum_ns
        / (long double)pipeline->stats.interval_count;
    return (double)(1000000000.0L / mean);
}

double motion_pipeline_jitter_mean_ms(const MotionPipeline *pipeline)
{
    if (pipeline == NULL || pipeline->stats.interval_count == 0) {
        return 0.0;
    }
    return (double)(pipeline->stats.jitter_sum_ns
        / (long double)pipeline->stats.interval_count / 1000000.0L);
}

double motion_pipeline_jitter_max_ms(const MotionPipeline *pipeline)
{
    return pipeline == NULL
        ? 0.0
        : (double)pipeline->stats.jitter_max_ns / 1000000.0;
}

bool motion_sample_to_dsu_timestamp(
    MotionDsuTimeline *timeline,
    const MotionSample *sample,
    uint64_t now_ns,
    uint64_t max_age_ns,
    uint64_t *timestamp_us
)
{
    if (timeline == NULL || sample == NULL || timestamp_us == NULL
        || sample->timestamp_ns == 0) {
        return false;
    }

    const uint64_t received_ns = sample->received_timestamp_ns != 0
        ? sample->received_timestamp_ns
        : sample->timestamp_ns;
    if (now_ns < received_ns || now_ns - received_ns > max_age_ns) {
        return false;
    }

    uint64_t candidate = sample->timestamp_ns / 1000ULL;
    if (candidate <= timeline->last_timestamp_us) {
        candidate = timeline->last_timestamp_us + 1ULL;
    }
    timeline->last_timestamp_us = candidate;
    *timestamp_us = candidate;
    return true;
}