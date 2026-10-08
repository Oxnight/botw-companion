#include "motion_pipeline.h"

#include <assert.h>
#include <math.h>
#include <stdint.h>

static DsuVec3 vec(float x, float y, float z)
{
    return (DsuVec3){x, y, z};
}

int main(void)
{
    MotionPipeline pipeline;
    MotionSample sample = {0};
    motion_pipeline_reset(&pipeline);

    /* A complete sample retains the sensor's actual timestamp. */
    assert(!motion_pipeline_push(
        &pipeline, MOTION_SENSOR_GYRO, vec(1.0f, 2.0f, 3.0f),
        100000000ULL, 500000000ULL, &sample
    ));
    assert(motion_pipeline_push(
        &pipeline, MOTION_SENSOR_ACCEL, vec(4.0f, 5.0f, 6.0f),
        100000000ULL, 500000100ULL, &sample
    ));
    assert(sample.timestamp_ns == 500000000ULL);
    assert(sample.received_timestamp_ns == 500000100ULL);
    assert(sample.gyro_rad_s.x == 1.0f);
    assert(sample.accel_ms2.z == 6.0f);
    const MotionPipelineStats *stats = motion_pipeline_stats(&pipeline);
    assert(stats != NULL);
    assert(stats->sensor_events == 2);
    assert(stats->accepted_gyro == 1 && stats->accepted_accel == 1);
    assert(stats->emitted_samples == 1);

    /* Never emit duplicates or regressing timestamps. */
    assert(!motion_pipeline_push(
        &pipeline, MOTION_SENSOR_ACCEL, vec(7.0f, 8.0f, 9.0f),
        100000000ULL, 500000200ULL, &sample
    ));
    assert(motion_pipeline_stats(&pipeline)->duplicate_timestamps == 1);
    assert(!motion_pipeline_push(
        &pipeline, MOTION_SENSOR_GYRO, vec(9.0f, 9.0f, 9.0f),
        99999999ULL, 500000300ULL, &sample
    ));
    assert(motion_pipeline_stats(&pipeline)->regressive_timestamps == 1);

    /* Do not pair a gyro sample too far from the accelerometer sample. */
    assert(!motion_pipeline_push(
        &pipeline, MOTION_SENSOR_ACCEL, vec(1.0f, 1.0f, 1.0f),
        110000000ULL, 510000000ULL, &sample
    ));

    /* Also accept the reverse accelerometer-then-gyro order. */
    motion_pipeline_reset(&pipeline);
    assert(!motion_pipeline_push(
        &pipeline, MOTION_SENSOR_ACCEL, vec(0.0f, 9.8f, 0.0f),
        200000000ULL, 600000000ULL, &sample
    ));
    assert(motion_pipeline_push(
        &pipeline, MOTION_SENSOR_GYRO, vec(0.1f, 0.2f, 0.3f),
        200000000ULL, 600000100ULL, &sample
    ));
    assert(sample.timestamp_ns == 600000000ULL);

    /* Use host time when the driver provides no timestamp. */
    motion_pipeline_reset(&pipeline);
    assert(!motion_pipeline_push(
        &pipeline, MOTION_SENSOR_GYRO, vec(2.0f, 0.0f, 0.0f),
        0, 700000000ULL, &sample
    ));
    assert(motion_pipeline_push(
        &pipeline, MOTION_SENSOR_ACCEL, vec(0.0f, 9.8f, 0.0f),
        0, 700100000ULL, &sample
    ));
    assert(sample.timestamp_ns == 700100000ULL);
    assert(motion_pipeline_stats(&pipeline)->fallback_timestamps == 2);

    /* Calculate sample rate and jitter from actual receive times. */
    motion_pipeline_reset(&pipeline);
    for (uint64_t i = 0; i < 3; ++i) {
        const uint64_t sensor_ns = 800000000ULL + i * 5000000ULL;
        const uint64_t host_ns = 900000000ULL + i * 5000000ULL;
        assert(!motion_pipeline_push(
            &pipeline, MOTION_SENSOR_GYRO, vec(0.1f, 0.2f, 0.3f),
            sensor_ns, host_ns, &sample
        ));
        assert(motion_pipeline_push(
            &pipeline, MOTION_SENSOR_ACCEL, vec(0.0f, 9.8f, 0.0f),
            sensor_ns, host_ns + 100ULL, &sample
        ));
    }
    assert(fabs(motion_pipeline_received_hz(&pipeline) - 200.0) < 0.001);
    assert(motion_pipeline_jitter_mean_ms(&pipeline) < 0.001);
    assert(motion_pipeline_jitter_max_ms(&pipeline) < 0.001);

    /* Three samples delivered together every 15 ms remain a 200 Hz stream. */
    motion_pipeline_reset(&pipeline);
    for (uint64_t i = 0; i < 7; ++i) {
        const uint64_t sensor_ns = 1000000000ULL + i * 5000000ULL;
        const uint64_t host_ns = 1100000000ULL + (i / 3ULL) * 15000000ULL;
        assert(!motion_pipeline_push(
            &pipeline, MOTION_SENSOR_GYRO, vec(0.1f, 0.2f, 0.3f),
            sensor_ns, host_ns, &sample
        ));
        assert(motion_pipeline_push(
            &pipeline, MOTION_SENSOR_ACCEL, vec(0.0f, 9.8f, 0.0f),
            sensor_ns, host_ns, &sample
        ));
    }
    assert(fabs(motion_pipeline_received_hz(&pipeline) - 200.0) < 0.001);

    DsuVec3 latest = {0};
    assert(motion_pipeline_latest_gyro(&pipeline, &latest));
    assert(latest.x == 0.1f);

    /* Reject a stale sample without advancing the DSU timeline. */
    MotionDsuTimeline timeline = {0};
    MotionSample timestamped = {
        .gyro_rad_s = vec(0.0f, 0.0f, 0.0f),
        .accel_ms2 = vec(0.0f, 9.8f, 0.0f),
        .timestamp_ns = 1000000000ULL,
        .received_timestamp_ns = 1000000000ULL,
    };
    uint64_t timestamp_us = 0;
    assert(!motion_sample_to_dsu_timestamp(
        &timeline, &timestamped, 1300000000ULL, 100000000ULL, &timestamp_us
    ));
    assert(timeline.last_timestamp_us == 0);

    /* Reconnection must never regress the transmitted timestamp. */
    assert(motion_sample_to_dsu_timestamp(
        &timeline, &timestamped, 1050000000ULL, 100000000ULL, &timestamp_us
    ));
    assert(timestamp_us == 1000000ULL);
    timestamped.timestamp_ns = 900000000ULL;
    timestamped.received_timestamp_ns = 900000000ULL;
    assert(motion_sample_to_dsu_timestamp(
        &timeline, &timestamped, 950000000ULL, 100000000ULL, &timestamp_us
    ));
    assert(timestamp_us == 1000001ULL);

    /*
     * The hardware clock may be ahead of SDL. Freshness depends exclusively on
     * receive time, never on the other clock.
     */
    timestamped.timestamp_ns = 5000000000ULL;
    timestamped.received_timestamp_ns = 2000000000ULL;
    assert(motion_sample_to_dsu_timestamp(
        &timeline, &timestamped, 2005000000ULL, 100000000ULL, &timestamp_us
    ));
    assert(timestamp_us == 5000000ULL);

    timestamped.received_timestamp_ns = 1800000000ULL;
    assert(!motion_sample_to_dsu_timestamp(
        &timeline, &timestamped, 2005000000ULL, 100000000ULL, &timestamp_us
    ));

    return 0;
}
