#include "telemetry.h"

#include <assert.h>
#include <math.h>

int main(void)
{
    DsuTelemetry telemetry;
    telemetry_reset(&telemetry, 1000000000ULL);
    assert(telemetry.started_ns == 1000000000ULL);
    assert(telemetry.sent_packets == 0);

    telemetry_record_send(&telemetry, 2000000000ULL);
    telemetry_record_send(&telemetry, 2005000000ULL);
    telemetry_record_send(&telemetry, 2010500000ULL);
    assert(telemetry.sent_packets == 3);
    assert(fabs(telemetry_send_hz(&telemetry) - 190.476190) < 0.001);
    assert(fabs(telemetry_send_jitter_mean_ms(&telemetry) - 0.25) < 0.001);
    assert(fabs(telemetry_send_jitter_max_ms(&telemetry) - 0.5) < 0.001);

    telemetry_pause_sends(&telemetry);
    telemetry_record_send(&telemetry, 5000000000ULL);
    assert(telemetry.sent_packets == 4);
    assert(telemetry.send_interval_count == 2);

    return 0;
}
