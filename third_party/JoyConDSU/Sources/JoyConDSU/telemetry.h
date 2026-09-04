#ifndef JOYCON_DSU_TELEMETRY_H
#define JOYCON_DSU_TELEMETRY_H

#include "calibration.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
    uint64_t started_ns;
    uint64_t sent_packets;
    uint64_t send_errors;
    uint64_t stale_samples;
    uint64_t nonfinite_samples;
    uint64_t requests_received;
    uint64_t invalid_requests;
    uint64_t crc_compat_requests;
    uint64_t clients_created;
    uint64_t clients_expired;
    uint64_t disconnects;
    uint64_t reconnects;
    uint64_t calibrations_valid;
    uint64_t calibrations_rejected;
    uint64_t last_send_ns;
    uint64_t send_interval_count;
    long double send_interval_sum_ns;
    long double send_jitter_sum_ns;
    uint64_t send_jitter_max_ns;
    CalibrationResult last_calibration;
    bool calibration_valid;
} DsuTelemetry;

void telemetry_reset(DsuTelemetry *telemetry, uint64_t now_ns);
void telemetry_record_send(DsuTelemetry *telemetry, uint64_t now_ns);
void telemetry_pause_sends(DsuTelemetry *telemetry);
double telemetry_send_hz(const DsuTelemetry *telemetry);
double telemetry_send_jitter_mean_ms(const DsuTelemetry *telemetry);
double telemetry_send_jitter_max_ms(const DsuTelemetry *telemetry);

#endif
