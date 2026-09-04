#ifndef JOYCON_DSU_MOTION_PIPELINE_H
#define JOYCON_DSU_MOTION_PIPELINE_H

#include "dsu_protocol.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    MOTION_HISTORY_SIZE = 32,
};

typedef enum {
    MOTION_SENSOR_GYRO = 1,
    MOTION_SENSOR_ACCEL = 2,
} MotionSensorKind;

typedef struct {
    DsuVec3 gyro_rad_s;
    DsuVec3 accel_ms2;
    /* Horloge matérielle alignée : transmise à Ryujinx. */
    uint64_t timestamp_ns;
    /* Horloge SDL de réception : utilisée uniquement pour contrôler l'âge. */
    uint64_t received_timestamp_ns;
} MotionSample;

typedef struct {
    DsuVec3 value;
    uint64_t timestamp_ns;
    uint64_t received_timestamp_ns;
    bool valid;
} TimedMotionValue;

typedef struct {
    uint64_t sensor_events;
    uint64_t accepted_gyro;
    uint64_t accepted_accel;
    uint64_t emitted_samples;
    uint64_t duplicate_timestamps;
    uint64_t regressive_timestamps;
    uint64_t invalid_values;
    uint64_t fallback_timestamps;
    uint64_t pairing_waits;
    uint64_t last_received_ns;
    uint64_t interval_count;
    long double interval_sum_ns;
    long double jitter_sum_ns;
    uint64_t jitter_max_ns;
} MotionPipelineStats;

typedef struct {
    TimedMotionValue gyro[MOTION_HISTORY_SIZE];
    size_t gyro_next;
    TimedMotionValue accel[MOTION_HISTORY_SIZE];
    size_t accel_next;
    uint64_t last_gyro_timestamp_ns;
    uint64_t last_accel_timestamp_ns;
    uint64_t last_emitted_timestamp_ns;
    DsuVec3 latest_gyro_rad_s;
    bool has_latest_gyro;
    uint64_t sensor_origin_ns;
    uint64_t host_origin_ns;
    MotionPipelineStats stats;
} MotionPipeline;

typedef struct {
    uint64_t last_timestamp_us;
} MotionDsuTimeline;

void motion_pipeline_reset(MotionPipeline *pipeline);

/*
 * Ajoute une mesure SDL déjà normalisée. Pour une mesure d'accéléromètre,
 * retourne true uniquement lorsqu'un échantillon gyro compatible et inédit
 * permet de construire une mesure DSU complète.
 */
bool motion_pipeline_push(
    MotionPipeline *pipeline,
    MotionSensorKind kind,
    DsuVec3 value,
    uint64_t sensor_timestamp_ns,
    uint64_t fallback_timestamp_ns,
    MotionSample *sample
);

bool motion_pipeline_latest_gyro(
    const MotionPipeline *pipeline,
    DsuVec3 *gyro_rad_s
);

const MotionPipelineStats *motion_pipeline_stats(const MotionPipeline *pipeline);
double motion_pipeline_received_hz(const MotionPipeline *pipeline);
double motion_pipeline_jitter_mean_ms(const MotionPipeline *pipeline);
double motion_pipeline_jitter_max_ms(const MotionPipeline *pipeline);

/*
 * Refuse une mesure trop ancienne puis produit une date DSU strictement
 * monotone, même si l'horloge matérielle repart de zéro après reconnexion.
 */
bool motion_sample_to_dsu_timestamp(
    MotionDsuTimeline *timeline,
    const MotionSample *sample,
    uint64_t now_ns,
    uint64_t max_age_ns,
    uint64_t *timestamp_us
);

#ifdef __cplusplus
}
#endif

#endif
