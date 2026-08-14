#include "telemetry.h"

#include <string.h>

static const uint64_t EXPECTED_INTERVAL_NS = 5000000ULL;

void telemetry_reset(DsuTelemetry *telemetry, uint64_t now_ns)
{
    if (telemetry != NULL) {
        memset(telemetry, 0, sizeof(*telemetry));
        telemetry->started_ns = now_ns;
    }
}

void telemetry_record_send(DsuTelemetry *telemetry, uint64_t now_ns)
{
    if (telemetry == NULL) {
        return;
    }
    if (telemetry->last_send_ns != 0 && now_ns > telemetry->last_send_ns) {
        const uint64_t interval = now_ns - telemetry->last_send_ns;
        const uint64_t jitter = interval >= EXPECTED_INTERVAL_NS
            ? interval - EXPECTED_INTERVAL_NS
            : EXPECTED_INTERVAL_NS - interval;
        telemetry->send_interval_count += 1;
        telemetry->send_interval_sum_ns += (long double)interval;
        telemetry->send_jitter_sum_ns += (long double)jitter;
        if (jitter > telemetry->send_jitter_max_ns) {
            telemetry->send_jitter_max_ns = jitter;
        }
    }
    telemetry->last_send_ns = now_ns;
    telemetry->sent_packets += 1;
}

void telemetry_pause_sends(DsuTelemetry *telemetry)
{
    if (telemetry != NULL) {
        /* Une absence de client n'est pas du jitter réseau. */
        telemetry->last_send_ns = 0;
    }
}

double telemetry_send_hz(const DsuTelemetry *telemetry)
{
    if (telemetry == NULL || telemetry->send_interval_count == 0
        || telemetry->send_interval_sum_ns <= 0.0L) {
        return 0.0;
    }
    return (double)(1000000000.0L /
        (telemetry->send_interval_sum_ns
            / (long double)telemetry->send_interval_count));
}

double telemetry_send_jitter_mean_ms(const DsuTelemetry *telemetry)
{
    if (telemetry == NULL || telemetry->send_interval_count == 0) {
        return 0.0;
    }
    return (double)(telemetry->send_jitter_sum_ns
        / (long double)telemetry->send_interval_count / 1000000.0L);
}

double telemetry_send_jitter_max_ms(const DsuTelemetry *telemetry)
{
    return telemetry == NULL
        ? 0.0
        : (double)telemetry->send_jitter_max_ns / 1000000.0;
}