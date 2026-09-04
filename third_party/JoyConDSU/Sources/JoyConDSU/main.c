#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>

#include "calibration.h"
#include "dsu_clients.h"
#include "dsu_protocol.h"
#include "motion_pipeline.h"
#include "platform_runtime.h"
#include "platform_socket.h"
#include "telemetry.h"

#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum {
    RECEIVE_BUFFER_SIZE = 1024,
    MAX_REQUESTS_PER_TURN = 64,
    CALIBRATION_WARMUP_SAMPLES = 60,
    CLIENT_TIMEOUT_SECONDS = 5,
};

static const uint64_t NS_PER_SECOND = 1000000000ULL;
static const uint64_t CLIENT_TIMEOUT_NS =
    (uint64_t)CLIENT_TIMEOUT_SECONDS * 1000000000ULL;
static const uint64_t MAX_SAMPLE_AGE_NS = 100000000ULL;
static const uint64_t SENSOR_STALL_NS = 500000000ULL;
static const uint64_t TELEMETRY_INTERVAL_NS = 10000000000ULL;

static const float GRAVITY_MS2 = 9.80665f;
static const float RAD_TO_DEG = 57.29577951308232f;

/*
 * Locally administered, stable identifier for this virtual DSU controller.
 * It is intentionally not the Joy-Con's hardware Bluetooth address.
 */
static const uint8_t CONTROLLER_MAC[6] = {
    0x02, 0x4a, 0x43, 0x44, 0x53, 0x55
};

typedef struct {
    SDL_Gamepad *gamepad;
    SDL_JoystickID instance_id;
    SDL_GamepadType type;
    uint16_t vendor_id;
    uint16_t product_id;
    char name[256];
    char path[1024];
    float gyro_rate_hz;
    float accel_rate_hz;
    DsuVec3 gyro_bias_rad_s;
    MotionPipeline motion;
    MotionSample latest_sample;
    bool has_latest_sample;
    uint64_t last_complete_sample_host_ns;
} Controller;

static uint32_t make_server_id(void)
{
    const uint64_t now = SDL_GetTicksNS();
    const uint32_t pid = dsu_platform_process_id();
    uint32_t x = (uint32_t)(now ^ (now >> 32) ^ pid ^ 0x4a434453u);

    /* xorshift32: deterministic inside one call, no global PRNG state needed. */
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;

    return x == 0u ? 1u : x;
}

static void print_client(const DsuSocketAddress *address)
{
    char ip[64] = {0};
    if (!dsu_socket_address_ipv4_text(address, ip, sizeof(ip))) {
        return;
    }
    printf("Client DSU connecté : %s:%u\n", ip, dsu_socket_address_port(address));
}

static bool controller_has_motion(SDL_Gamepad *gamepad)
{
    return SDL_GamepadHasSensor(gamepad, SDL_SENSOR_GYRO)
        && SDL_GamepadHasSensor(gamepad, SDL_SENSOR_ACCEL);
}

static bool is_single_joycon_type(SDL_GamepadType type)
{
    return type == SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_JOYCON_LEFT
        || type == SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_JOYCON_RIGHT;
}

static int gamepad_priority(SDL_Gamepad *gamepad)
{
    const SDL_GamepadType type = SDL_GetGamepadType(gamepad);

    if (type == SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_JOYCON_PAIR) {
        return 100;
    }
    if (type == SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_PRO) {
        return 80;
    }
    if (is_single_joycon_type(type)) {
        return 5;
    }
    return controller_has_motion(gamepad) ? 10 : 0;
}

static void copy_controller_identity(Controller *controller, SDL_Gamepad *gamepad)
{
    const char *name = SDL_GetGamepadName(gamepad);
    controller->vendor_id = SDL_GetGamepadVendor(gamepad);
    controller->product_id = SDL_GetGamepadProduct(gamepad);
    snprintf(
        controller->name,
        sizeof(controller->name),
        "%s",
        name != NULL ? name : "Contrôleur inconnu"
    );
    const char *path = SDL_GetGamepadPath(gamepad);
    snprintf(
        controller->path,
        sizeof(controller->path),
        "%s",
        path != NULL ? path : ""
    );
}

static bool enable_controller_sensors(Controller *controller)
{
    if (!SDL_SetGamepadSensorEnabled(controller->gamepad, SDL_SENSOR_GYRO, true)) {
        fprintf(stderr, "Impossible d'activer le gyro : %s\n", SDL_GetError());
        return false;
    }
    if (!SDL_SetGamepadSensorEnabled(controller->gamepad, SDL_SENSOR_ACCEL, true)) {
        fprintf(stderr, "Impossible d'activer l'accéléromètre : %s\n", SDL_GetError());
        return false;
    }

    controller->gyro_rate_hz =
        SDL_GetGamepadSensorDataRate(controller->gamepad, SDL_SENSOR_GYRO);
    controller->accel_rate_hz =
        SDL_GetGamepadSensorDataRate(controller->gamepad, SDL_SENSOR_ACCEL);
    motion_pipeline_reset(&controller->motion);
    return true;
}

static bool adopt_controller(
    Controller *controller,
    SDL_Gamepad *gamepad,
    SDL_JoystickID instance_id
)
{
    if (!controller_has_motion(gamepad)) {
        SDL_CloseGamepad(gamepad);
        return false;
    }

    controller->gamepad = gamepad;
    controller->instance_id = instance_id;
    controller->type = SDL_GetGamepadType(gamepad);
    copy_controller_identity(controller, gamepad);

    if (!enable_controller_sensors(controller)) {
        SDL_CloseGamepad(gamepad);
        memset(controller, 0, sizeof(*controller));
        return false;
    }
    return true;
}

static bool controller_matches_identity(
    SDL_Gamepad *gamepad,
    const Controller *wanted
)
{
    if (wanted->name[0] == '\0') {
        return false;
    }

    const char *candidate_path = SDL_GetGamepadPath(gamepad);
    if (wanted->path[0] != '\0'
        && candidate_path != NULL
        && strcmp(candidate_path, wanted->path) == 0) {
        return true;
    }

    const char *name = SDL_GetGamepadName(gamepad);
    if (name == NULL || strcmp(name, wanted->name) != 0) {
        return false;
    }
    if (wanted->vendor_id != 0
        && SDL_GetGamepadVendor(gamepad) != wanted->vendor_id) {
        return false;
    }
    if (wanted->product_id != 0
        && SDL_GetGamepadProduct(gamepad) != wanted->product_id) {
        return false;
    }
    return SDL_GetGamepadType(gamepad) == wanted->type;
}

static bool open_controller(
    Controller *controller,
    SDL_JoystickID requested_id,
    const char *requested_path,
    bool require_requested,
    bool reconnect_identity,
    const Controller *wanted
)
{
    int count = 0;
    SDL_JoystickID *ids = SDL_GetGamepads(&count);

    if (ids == NULL || count <= 0) {
        SDL_free(ids);
        return false;
    }

    SDL_Gamepad *best = NULL;
    SDL_JoystickID best_id = 0;
    int best_priority = -1;

    for (int i = 0; i < count; ++i) {
        SDL_Gamepad *candidate = SDL_OpenGamepad(ids[i]);
        if (candidate == NULL) {
            continue;
        }

        bool match = false;
        const int priority = gamepad_priority(candidate);

        if (require_requested && !reconnect_identity) {
            const char *candidate_path = SDL_GetGamepadPath(candidate);
            match = requested_path != NULL && requested_path[0] != '\0'
                ? candidate_path != NULL && strcmp(candidate_path, requested_path) == 0
                : ids[i] == requested_id;
        } else if (reconnect_identity) {
            match = wanted != NULL && controller_matches_identity(candidate, wanted);
        } else {
            match = priority > best_priority && controller_has_motion(candidate);
        }

        if (match && controller_has_motion(candidate)) {
            if (best != NULL) {
                SDL_CloseGamepad(best);
            }
            best = candidate;
            best_id = ids[i];
            best_priority = priority;
            if (require_requested || reconnect_identity) {
                break;
            }
        } else {
            SDL_CloseGamepad(candidate);
        }
    }

    SDL_free(ids);

    if (best == NULL) {
        return false;
    }

    return adopt_controller(controller, best, best_id);
}

static const char *gamepad_type_name(SDL_GamepadType type)
{
    const char *name = SDL_GetGamepadStringForType(type);
    return name != NULL ? name : "unknown";
}

static void print_inventory(void)
{
    int count = 0;
    SDL_JoystickID *ids = SDL_GetGamepads(&count);

    printf("BOTW_DSU_CONTROLLERS\t1\n");
    if (ids == NULL || count <= 0) {
        SDL_free(ids);
        return;
    }

    for (int i = 0; i < count; ++i) {
        SDL_Gamepad *gamepad = SDL_OpenGamepad(ids[i]);
        if (gamepad == NULL) {
            continue;
        }

        const char *name = SDL_GetGamepadName(gamepad);
        const char *path = SDL_GetGamepadPath(gamepad);
        const SDL_GamepadType type = SDL_GetGamepadType(gamepad);
        const bool gyro = SDL_GamepadHasSensor(gamepad, SDL_SENSOR_GYRO);
        const bool accel = SDL_GamepadHasSensor(gamepad, SDL_SENSOR_ACCEL);

        printf(
            "CONTROLLER\t%u\t%u\t%u\t%d\t%d\t%d\t%s\t%s\t%s\n",
            (unsigned int)ids[i],
            (unsigned int)SDL_GetGamepadVendor(gamepad),
            (unsigned int)SDL_GetGamepadProduct(gamepad),
            (int)type,
            gyro ? 1 : 0,
            accel ? 1 : 0,
            gamepad_type_name(type),
            name != NULL ? name : "Contrôleur inconnu",
            path != NULL ? path : ""
        );
        SDL_CloseGamepad(gamepad);
    }

    SDL_free(ids);
}

static void close_controller(Controller *controller)
{
    if (controller->gamepad != NULL) {
        SDL_CloseGamepad(controller->gamepad);
    }

    memset(controller, 0, sizeof(*controller));
}

static bool ingest_sensor_event(
    Controller *controller,
    const SDL_GamepadSensorEvent *event,
    MotionSample *sample
)
{
    if (controller->gamepad == NULL
        || event->which != controller->instance_id) {
        return false;
    }

    MotionSensorKind kind;
    if (event->sensor == SDL_SENSOR_GYRO) {
        kind = MOTION_SENSOR_GYRO;
    } else if (event->sensor == SDL_SENSOR_ACCEL) {
        kind = MOTION_SENSOR_ACCEL;
    } else {
        return false;
    }

    const DsuVec3 value = {
        event->data[0],
        event->data[1],
        event->data[2],
    };
    return motion_pipeline_push(
        &controller->motion,
        kind,
        value,
        event->sensor_timestamp,
        event->timestamp,
        sample
    );
}

static bool wait_for_motion_sample(
    Controller *controller,
    MotionSample *sample,
    uint32_t timeout_ms
)
{
    const uint64_t deadline =
        SDL_GetTicksNS() + (uint64_t)timeout_ms * 1000000ULL;

    while (!dsu_platform_stop_requested() && SDL_GetTicksNS() < deadline) {
        SDL_Event event;
        const uint64_t remaining_ns = deadline - SDL_GetTicksNS();
        const Sint32 remaining_ms = (Sint32)fmax(
            1.0,
            ceil((double)remaining_ns / 1000000.0)
        );

        if (!SDL_WaitEventTimeout(&event, remaining_ms)) {
            continue;
        }

        if (event.type == SDL_EVENT_GAMEPAD_REMOVED
            && event.gdevice.which == controller->instance_id) {
            return false;
        }

        if (event.type == SDL_EVENT_GAMEPAD_SENSOR_UPDATE
            && ingest_sensor_event(controller, &event.gsensor, sample)) {
            return true;
        }
    }

    return false;
}

static bool calibrate_controller(
    Controller *controller,
    DsuTelemetry *telemetry
)
{
    for (int attempt = 1; attempt <= 3; ++attempt) {
        printf("\nCalibration gyro (%d/3)\n", attempt);
        printf("Pose la manette IMMOBILE sur une surface stable...\n");

        SDL_Delay(300);
        SDL_FlushEvents(
            SDL_EVENT_GAMEPAD_SENSOR_UPDATE,
            SDL_EVENT_GAMEPAD_SENSOR_UPDATE
        );
        motion_pipeline_reset(&controller->motion);

        /*
         * Laisse le flux Bluetooth et les deux capteurs se resynchroniser.
         * Ces mesures ne doivent jamais participer au calcul du biais.
         */
        bool warmup_ok = true;
        for (size_t i = 0; i < CALIBRATION_WARMUP_SAMPLES; ++i) {
            MotionSample ignored = {0};
            if (!wait_for_motion_sample(controller, &ignored, 250)) {
                warmup_ok = false;
                break;
            }
        }
        if (!warmup_ok) {
            fprintf(stderr, "Flux capteur interrompu pendant la stabilisation.\n");
            return false;
        }

        CalibrationCollector collector;
        calibration_reset(&collector);
        CalibrationStatus collection_status = CALIBRATION_PENDING;

        for (size_t sample = 0; sample < CALIBRATION_REQUIRED_SAMPLES; ++sample) {
            MotionSample motion = {0};
            if (!wait_for_motion_sample(controller, &motion, 250)) {
                fprintf(stderr, "Flux capteur interrompu pendant la calibration.\n");
                return false;
            }
            collection_status = calibration_push(&collector, &motion);
            if (collection_status != CALIBRATION_PENDING
                && collection_status != CALIBRATION_VALID) {
                break;
            }
        }

        CalibrationResult result = calibration_evaluate(&collector);
        if (collection_status != CALIBRATION_VALID
            || result.status != CALIBRATION_VALID) {
            telemetry->calibrations_rejected += 1;
            const CalibrationStatus reason =
                collection_status != CALIBRATION_VALID
                    ? collection_status
                    : result.status;
            fprintf(
                stderr,
                "Calibration refusée : %s (durée %.2fs, cadence %.1f Hz, "
                "accel %.3fg, σ %.3fg).\n",
                calibration_status_message(reason),
                result.duration_seconds,
                result.effective_rate_hz,
                result.accel_mean_g,
                result.accel_stddev_g
            );

            if (attempt < 3) {
                fprintf(stderr, "On recommence : ne touche pas à la manette.\n");
            }

            continue;
        }

        controller->gyro_bias_rad_s = result.gyro_bias_rad_s;
        telemetry->last_calibration = result;
        telemetry->calibration_valid = true;
        telemetry->calibrations_valid += 1;
        motion_pipeline_reset(&controller->motion);

        printf("Calibration validée\n");
        printf(
            "   biais : X %+0.4f°/s | Y %+0.4f°/s | Z %+0.4f°/s\n",
            controller->gyro_bias_rad_s.x * RAD_TO_DEG,
            controller->gyro_bias_rad_s.y * RAD_TO_DEG,
            controller->gyro_bias_rad_s.z * RAD_TO_DEG
        );
        printf(
            "   qualité : %.1f Hz | gyro σ %.4f/%.4f/%.4f°/s | accel %.3fg\n",
            result.effective_rate_hz,
            result.gyro_stddev_rad_s.x * RAD_TO_DEG,
            result.gyro_stddev_rad_s.y * RAD_TO_DEG,
            result.gyro_stddev_rad_s.z * RAD_TO_DEG,
            result.accel_mean_g
        );

        return true;
    }

    fprintf(stderr, "Calibration refusée après 3 essais.\n");
    return false;
}

static void process_requests(
    DsuSocket socket_handle,
    DsuClientRegistry *clients,
    uint32_t server_id,
    bool controller_connected,
    bool *crc_warning_printed,
    DsuTelemetry *telemetry
)
{
    for (size_t request_index = 0;
         request_index < MAX_REQUESTS_PER_TURN;
         ++request_index) {
        uint8_t packet[RECEIVE_BUFFER_SIZE] = {0};
        DsuSocketAddress sender = {0};
        DsuSocklen sender_len = (DsuSocklen)sizeof(sender);

        const DsuIoSize received = dsu_socket_receive(
            socket_handle,
            packet,
            sizeof(packet),
            &sender,
            &sender_len
        );

        if (received < 0) {
            if (dsu_socket_last_error_would_block()) {
                return;
            }
            dsu_socket_print_last_error("recvfrom");
            return;
        }
        telemetry->requests_received += 1;

        const DsuParsedPacket parsed =
            dsu_parse_client_packet(packet, (size_t)received);

        if (!parsed.valid) {
            telemetry->invalid_requests += 1;
            continue;
        }

        if (!dsu_request_shape_valid(packet, &parsed)) {
            telemetry->invalid_requests += 1;
            continue;
        }

        /*
         * Ryujinx builds have existed that send locally usable DSU requests
         * whose CRC does not validate exactly like the public reference.
         * Since this server is bound exclusively to 127.0.0.1, we keep
         * compatibility while making the deviation visible once.
         */
        if (!parsed.crc_valid && !*crc_warning_printed) {
            fprintf(
                stderr,
                "Client local avec CRC DSU non conforme : accepté en mode localhost.\n"
            );
            *crc_warning_printed = true;
        }
        telemetry->crc_compat_requests += parsed.crc_valid ? 0u : 1u;

        if (parsed.message_type == DSU_MSG_VERSION) {
            uint8_t response[DSU_PACKET_VERSION_SIZE];
            dsu_build_version_response(response, server_id);
            (void)dsu_socket_send(
                socket_handle, response, sizeof(response), &sender, sender_len
            );
            continue;
        }

        if (parsed.message_type == DSU_MSG_PORTS) {
            if (parsed.effective_size < 24) {
                continue;
            }

            const int32_t requested =
                (int32_t)dsu_read_u32_le(packet, 20);

            if (requested < 0 || requested > 4) {
                continue;
            }

            if (parsed.effective_size < 24u + (size_t)requested) {
                continue;
            }

            for (int32_t i = 0; i < requested; ++i) {
                const uint8_t slot = packet[24u + (size_t)i];
                if (slot > 3u) {
                    continue;
                }

                uint8_t response[DSU_PACKET_PORT_INFO_SIZE];
                dsu_build_port_info_response(
                    response,
                    server_id,
                    slot,
                    controller_connected && slot == 0u,
                    CONTROLLER_MAC
                );

                (void)dsu_socket_send(
                    socket_handle, response, sizeof(response), &sender, sender_len
                );
            }

            continue;
        }

        if (parsed.message_type != DSU_MSG_DATA || !controller_connected) {
            continue;
        }

        if (!dsu_subscription_matches(
                packet,
                parsed.effective_size,
                0,
                CONTROLLER_MAC
            )) {
            continue;
        }

        bool is_new = false;
        DsuClient *client = dsu_clients_subscribe(
            clients,
            &sender,
            sender_len,
            SDL_GetTicksNS(),
            &is_new
        );

        if (client == NULL) {
            fprintf(stderr, "Limite de clients DSU atteinte.\n");
            continue;
        }

        if (is_new) {
            telemetry->clients_created += 1;
            print_client(&sender);
        }
    }
}

static void send_motion_to_clients(
    DsuSocket socket_handle,
    DsuClientRegistry *clients,
    uint32_t server_id,
    const Controller *controller,
    const MotionSample *motion,
    MotionDsuTimeline *timeline,
    uint64_t *total_packets,
    DsuTelemetry *telemetry
)
{
    const DsuVec3 gyro_deg_s = {
        (motion->gyro_rad_s.x - controller->gyro_bias_rad_s.x) * RAD_TO_DEG,
        (motion->gyro_rad_s.y - controller->gyro_bias_rad_s.y) * RAD_TO_DEG,
        (motion->gyro_rad_s.z - controller->gyro_bias_rad_s.z) * RAD_TO_DEG,
    };

    const DsuVec3 accel_g = {
        motion->accel_ms2.x / GRAVITY_MS2,
        motion->accel_ms2.y / GRAVITY_MS2,
        motion->accel_ms2.z / GRAVITY_MS2,
    };

    if (!dsu_motion_values_finite(accel_g, gyro_deg_s)) {
        telemetry->nonfinite_samples += 1;
        return;
    }

    const uint64_t now_ns = SDL_GetTicksNS();
    uint64_t timestamp_us = 0;
    if (!motion_sample_to_dsu_timestamp(
            timeline,
            motion,
            now_ns,
            MAX_SAMPLE_AGE_NS,
            &timestamp_us
        )) {
        telemetry->stale_samples += 1;
        return;
    }

    telemetry->clients_expired +=
        dsu_clients_expire(clients, now_ns, CLIENT_TIMEOUT_NS);
    if (dsu_clients_active_count(clients) == 0) {
        telemetry_pause_sends(telemetry);
        return;
    }
    for (size_t i = 0; i < DSU_MAX_CLIENTS; ++i) {
        DsuClient *client = &clients->entries[i];

        if (!client->active) {
            continue;
        }

        uint8_t packet[DSU_PACKET_DATA_SIZE];
        if (!dsu_build_controller_data(
            packet,
            server_id,
            client->packet_number,
            CONTROLLER_MAC,
            timestamp_us,
            accel_g,
            gyro_deg_s
        )) {
            continue;
        }
        client->packet_number += 1u;

        if (dsu_socket_send(
                socket_handle,
                packet,
                sizeof(packet),
                &client->address,
                client->address_len
            )) {
            *total_packets += 1;
            telemetry_record_send(telemetry, now_ns);
        } else {
            telemetry->send_errors += 1;
        }
    }
}

static bool controller_available(
    const Controller *controller,
    const DsuTelemetry *telemetry,
    uint64_t now_ns
)
{
    if (controller == NULL || telemetry == NULL
        || controller->gamepad == NULL || !telemetry->calibration_valid
        || controller->last_complete_sample_host_ns == 0
        || now_ns < controller->last_complete_sample_host_ns
        || now_ns - controller->last_complete_sample_host_ns > MAX_SAMPLE_AGE_NS) {
        return false;
    }

    return true;
}

static bool telemetry_health_ok(
    const Controller *controller,
    const DsuTelemetry *telemetry,
    uint64_t now_ns
)
{
    if (!controller_available(controller, telemetry, now_ns)) {
        return false;
    }

    const MotionPipelineStats *stats =
        motion_pipeline_stats(&controller->motion);
    if (stats == NULL || stats->interval_count < 20) {
        return true;
    }

    const double received_hz =
        motion_pipeline_received_hz(&controller->motion);
    return received_hz >= 120.0 && received_hz <= 260.0;
}

static void handle_runtime_event(
    const SDL_Event *event,
    Controller *controller,
    DsuSocket socket_handle,
    DsuClientRegistry *clients,
    uint32_t server_id,
    MotionDsuTimeline *timeline,
    uint64_t *total_packets,
    DsuTelemetry *telemetry
)
{
    if (event->type == SDL_EVENT_GAMEPAD_REMOVED
        && controller->gamepad != NULL
        && event->gdevice.which == controller->instance_id) {
        fprintf(stderr, "\nJoy-Con déconnecté. Attente de reconnexion...\n");
        telemetry->disconnects += 1;
        telemetry->calibration_valid = false;
        close_controller(controller);
        return;
    }

    if (event->type == SDL_EVENT_GAMEPAD_SENSOR_UPDATE
        && controller->gamepad != NULL) {
        MotionSample motion = {0};
        if (ingest_sensor_event(controller, &event->gsensor, &motion)) {
            controller->latest_sample = motion;
            controller->has_latest_sample = true;
            controller->last_complete_sample_host_ns = SDL_GetTicksNS();
            send_motion_to_clients(
                socket_handle,
                clients,
                server_id,
                controller,
                &motion,
                timeline,
                total_packets,
                telemetry
            );
        }
    }
}

static void print_telemetry(
    const Controller *controller,
    const DsuClientRegistry *clients,
    const DsuTelemetry *telemetry,
    uint64_t now_ns
)
{
    const MotionPipelineStats *motion =
        motion_pipeline_stats(&controller->motion);
    const double age_ms = controller->last_complete_sample_host_ns == 0
        || now_ns < controller->last_complete_sample_host_ns
        ? -1.0
        : (double)(now_ns - controller->last_complete_sample_host_ns) / 1000000.0;
    const double uptime_s = telemetry->started_ns == 0
        || now_ns < telemetry->started_ns
        ? 0.0
        : (double)(now_ns - telemetry->started_ns) / 1000000000.0;

    printf(
        "\nTÉLÉMÉTRIE DSU | santé:%s | uptime %.0fs | clients %zu\n"
        "  Flux   reçu %.1f Hz | envoyé %.1f Hz | âge %.1f ms | "
        "jitter reçu %.3f/%.3f ms | envoyé %.3f/%.3f ms\n"
        "  Motion événements %llu | paires %llu | doublons %llu | "
        "régressifs %llu | attente paire %llu | secours horloge %llu | "
        "valeurs invalides %llu\n"
        "  Réseau paquets %llu | requêtes %llu | invalides %llu | "
        "CRC compat. %llu | erreurs UDP %llu | clients créés/expirés %llu/%llu\n"
        "  Cycle  échantillons anciens %llu | non-finis %llu | "
        "déconnexions/reconnexions %llu/%llu | calibrations valides/refusées "
        "%llu/%llu\n",
        telemetry_health_ok(controller, telemetry, now_ns) ? "OK" : "ATTENTION",
        uptime_s,
        dsu_clients_active_count(clients),
        motion_pipeline_received_hz(&controller->motion),
        telemetry_send_hz(telemetry),
        age_ms,
        motion_pipeline_jitter_mean_ms(&controller->motion),
        motion_pipeline_jitter_max_ms(&controller->motion),
        telemetry_send_jitter_mean_ms(telemetry),
        telemetry_send_jitter_max_ms(telemetry),
        (unsigned long long)(motion != NULL ? motion->sensor_events : 0),
        (unsigned long long)(motion != NULL ? motion->emitted_samples : 0),
        (unsigned long long)(motion != NULL ? motion->duplicate_timestamps : 0),
        (unsigned long long)(motion != NULL ? motion->regressive_timestamps : 0),
        (unsigned long long)(motion != NULL ? motion->pairing_waits : 0),
        (unsigned long long)(motion != NULL ? motion->fallback_timestamps : 0),
        (unsigned long long)(motion != NULL ? motion->invalid_values : 0),
        (unsigned long long)telemetry->sent_packets,
        (unsigned long long)telemetry->requests_received,
        (unsigned long long)telemetry->invalid_requests,
        (unsigned long long)telemetry->crc_compat_requests,
        (unsigned long long)telemetry->send_errors,
        (unsigned long long)telemetry->clients_created,
        (unsigned long long)telemetry->clients_expired,
        (unsigned long long)telemetry->stale_samples,
        (unsigned long long)telemetry->nonfinite_samples,
        (unsigned long long)telemetry->disconnects,
        (unsigned long long)telemetry->reconnects,
        (unsigned long long)telemetry->calibrations_valid,
        (unsigned long long)telemetry->calibrations_rejected
    );
    printf(
        "BOTW_DSU_TELEMETRY\tversion=1\thealth=%s\tuptime_s=%.1f\t"
        "clients=%zu\treceived_hz=%.3f\tsent_hz=%.3f\t"
        "sample_age_ms=%.3f\treceived_jitter_mean_ms=%.3f\t"
        "received_jitter_max_ms=%.3f\tsent_jitter_mean_ms=%.3f\t"
        "sent_jitter_max_ms=%.3f\tsensor_events=%llu\t"
        "paired_samples=%llu\tduplicate_timestamps=%llu\t"
        "regressive_timestamps=%llu\tfallback_timestamps=%llu\t"
        "invalid_values=%llu\tsent_packets=%llu\trequests=%llu\t"
        "invalid_requests=%llu\tsend_errors=%llu\tstale_samples=%llu\t"
        "nonfinite_samples=%llu\tdisconnects=%llu\treconnects=%llu\t"
        "calibrations_valid=%llu\tcalibrations_rejected=%llu\t"
        "calibration_valid=%d\n",
        telemetry_health_ok(controller, telemetry, now_ns) ? "ok" : "warning",
        uptime_s,
        dsu_clients_active_count(clients),
        motion_pipeline_received_hz(&controller->motion),
        telemetry_send_hz(telemetry),
        age_ms,
        motion_pipeline_jitter_mean_ms(&controller->motion),
        motion_pipeline_jitter_max_ms(&controller->motion),
        telemetry_send_jitter_mean_ms(telemetry),
        telemetry_send_jitter_max_ms(telemetry),
        (unsigned long long)(motion != NULL ? motion->sensor_events : 0),
        (unsigned long long)(motion != NULL ? motion->emitted_samples : 0),
        (unsigned long long)(motion != NULL ? motion->duplicate_timestamps : 0),
        (unsigned long long)(motion != NULL ? motion->regressive_timestamps : 0),
        (unsigned long long)(motion != NULL ? motion->fallback_timestamps : 0),
        (unsigned long long)(motion != NULL ? motion->invalid_values : 0),
        (unsigned long long)telemetry->sent_packets,
        (unsigned long long)telemetry->requests_received,
        (unsigned long long)telemetry->invalid_requests,
        (unsigned long long)telemetry->send_errors,
        (unsigned long long)telemetry->stale_samples,
        (unsigned long long)telemetry->nonfinite_samples,
        (unsigned long long)telemetry->disconnects,
        (unsigned long long)telemetry->reconnects,
        (unsigned long long)telemetry->calibrations_valid,
        (unsigned long long)telemetry->calibrations_rejected,
        telemetry->calibration_valid ? 1 : 0
    );
    fflush(stdout);
}

int main(int argc, char *argv[])
{
    if (!dsu_platform_install_stop_handler()) {
        fprintf(stderr, "Impossible d'installer le gestionnaire d'arrêt.\n");
        return EXIT_FAILURE;
    }

    SDL_JoystickID requested_controller_id = 0;
    const char *requested_controller_path = NULL;
    bool require_requested_controller = false;
    bool inventory_only = false;

    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--list-controllers") == 0) {
            inventory_only = true;
        } else if (strcmp(argv[i], "--controller-path") == 0 && i + 1 < argc) {
            requested_controller_path = argv[++i];
            require_requested_controller = true;
        } else if (strcmp(argv[i], "--controller-id") == 0 && i + 1 < argc) {
            char *end = NULL;
            const unsigned long parsed = strtoul(argv[++i], &end, 10);
            if (end == argv[i] || *end != '\0' || parsed == 0) {
                fprintf(stderr, "Identifiant de manette invalide.\n");
                dsu_platform_cleanup();
                return EXIT_FAILURE;
            }
            requested_controller_id = (SDL_JoystickID)parsed;
            require_requested_controller = true;
        }
    }

    /*
     * Force SDL's native HIDAPI path and the logical L/R pairing before the
     * gamepad subsystem starts. This makes Windows deterministic even when
     * another application changed SDL's process environment.
     */
    if (!SDL_SetHint(SDL_HINT_JOYSTICK_HIDAPI_JOY_CONS, "1")
        || !SDL_SetHint(SDL_HINT_JOYSTICK_HIDAPI_COMBINE_JOY_CONS, "1")) {
        fprintf(stderr, "Impossible de configurer la détection des Joy-Con.\n");
        dsu_platform_cleanup();
        return EXIT_FAILURE;
    }

    if (!SDL_Init(SDL_INIT_GAMEPAD | SDL_INIT_SENSOR)) {
        fprintf(stderr, "SDL_Init : %s\n", SDL_GetError());
        dsu_platform_cleanup();
        return EXIT_FAILURE;
    }

    if (inventory_only) {
        print_inventory();
        SDL_Quit();
        dsu_platform_cleanup();
        return EXIT_SUCCESS;
    }

    if (!dsu_socket_platform_init()) {
        SDL_Quit();
        dsu_platform_cleanup();
        return EXIT_FAILURE;
    }
    const DsuSocket socket_handle =
        dsu_socket_create_loopback_udp(DSU_DEFAULT_PORT);
    if (socket_handle == DSU_INVALID_SOCKET) {
        dsu_socket_platform_cleanup();
        SDL_Quit();
        dsu_platform_cleanup();
        return EXIT_FAILURE;
    }

    const uint32_t server_id = make_server_id();
    Controller controller = {0};
    Controller selected_identity = {0};
    DsuClientRegistry clients = {0};
    bool crc_warning_printed = false;
    uint64_t total_packets = 0;
    MotionDsuTimeline dsu_timeline = {0};
    DsuTelemetry telemetry;
    telemetry_reset(&telemetry, SDL_GetTicksNS());
    uint64_t last_status_ns = SDL_GetTicksNS();
    uint64_t last_telemetry_ns = last_status_ns;
    bool previously_connected = false;

    printf("\n╔══════════════════════════════════════════╗\n");
    printf("║              JoyConDSU                   ║\n");
    printf("╚══════════════════════════════════════════╝\n");
    printf("DSU : 127.0.0.1:%d | protocole %d\n",
           DSU_DEFAULT_PORT, DSU_PROTOCOL_VERSION);
    printf("Plateforme : %s\n", dsu_platform_name());
    printf("Traitement motion : calibration du biais uniquement\n");
    printf("Filtre / deadzone : aucun\n\n");

    while (!dsu_platform_stop_requested()) {
        SDL_Event event;

        while (SDL_PollEvent(&event)) {
            handle_runtime_event(
                &event,
                &controller,
                socket_handle,
                &clients,
                server_id,
                &dsu_timeline,
                &total_packets,
                &telemetry
            );
        }

        if (controller.gamepad == NULL) {
            if (open_controller(
                    &controller,
                    requested_controller_id,
                    requested_controller_path,
                    require_requested_controller,
                    previously_connected && require_requested_controller,
                    &selected_identity
                )) {
                const char *name = SDL_GetGamepadName(controller.gamepad);
                if (require_requested_controller && selected_identity.name[0] == '\0') {
                    selected_identity.type = controller.type;
                    selected_identity.vendor_id = controller.vendor_id;
                    selected_identity.product_id = controller.product_id;
                    snprintf(
                        selected_identity.name,
                        sizeof(selected_identity.name),
                        "%s",
                        controller.name
                    );
                    snprintf(
                        selected_identity.path,
                        sizeof(selected_identity.path),
                        "%s",
                        controller.path
                    );
                }

                printf(
                    "Contrôleur : %s\n"
                    "   type SDL %d%s\n"
                    "   gyro  %.2f Hz | accel %.2f Hz\n",
                    name != NULL ? name : "Inconnu",
                    (int)controller.type,
                    controller.type == SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_JOYCON_PAIR
                        ? " (paire Joy-Con / grip)"
                        : "",
                    controller.gyro_rate_hz,
                    controller.accel_rate_hz
                );

                if (!calibrate_controller(&controller, &telemetry)) {
                    if (dsu_platform_stop_requested()) {
                        break;
                    }

                    close_controller(&controller);
                    SDL_Delay(1000);
                    continue;
                }

                controller.last_complete_sample_host_ns = SDL_GetTicksNS();
                if (previously_connected) {
                    telemetry.reconnects += 1;
                }
                previously_connected = true;
                printf("READY - lance ou reprends ton émulateur.\n\n");
            } else {
                static uint64_t last_wait_message = 0;
                const uint64_t now = SDL_GetTicksNS();

                if (now - last_wait_message >= NS_PER_SECOND) {
                    printf("\rEn attente de la source gyroscope sélectionnée...   ");
                    fflush(stdout);
                    last_wait_message = now;
                }

                SDL_Delay(50);
            }
        }

        process_requests(
            socket_handle,
            &clients,
            server_id,
            /* La télémétrie ne doit jamais couper un flux frais et calibré. */
            controller_available(&controller, &telemetry, SDL_GetTicksNS()),
            &crc_warning_printed,
            &telemetry
        );

        if (controller.gamepad != NULL
            && !SDL_GamepadConnected(controller.gamepad)) {
            fprintf(stderr, "\nContrôleur perdu. Attente de reconnexion...\n");
            telemetry.disconnects += 1;
            telemetry.calibration_valid = false;
            close_controller(&controller);
            continue;
        }

        if (controller.gamepad != NULL
            && controller.last_complete_sample_host_ns != 0
            && SDL_GetTicksNS() - controller.last_complete_sample_host_ns
                > SENSOR_STALL_NS) {
            fprintf(
                stderr,
                "\nFlux capteur interrompu plus de 500 ms. Reconnexion et recalibration...\n"
            );
            telemetry.disconnects += 1;
            telemetry.calibration_valid = false;
            close_controller(&controller);
            continue;
        }

        if (controller.gamepad != NULL) {
            const uint64_t now = SDL_GetTicksNS();
            if (now - last_status_ns >= NS_PER_SECOND) {
                const size_t count = dsu_clients_active_count(&clients);

                if (count > 0) {
                    DsuVec3 gyro = {0};

                    if (motion_pipeline_latest_gyro(&controller.motion, &gyro)) {
                        printf(
                            "\rDSU ✓ clients:%zu packets:%llu gyro:%+6.2f %+6.2f %+6.2f °/s   ",
                            count,
                            (unsigned long long)total_packets,
                            (gyro.x - controller.gyro_bias_rad_s.x) * RAD_TO_DEG,
                            (gyro.y - controller.gyro_bias_rad_s.y) * RAD_TO_DEG,
                            (gyro.z - controller.gyro_bias_rad_s.z) * RAD_TO_DEG
                        );
                        fflush(stdout);
                    }
                }

                last_status_ns = now;
            }
            if (now - last_telemetry_ns >= TELEMETRY_INTERVAL_NS) {
                print_telemetry(&controller, &clients, &telemetry, now);
                last_telemetry_ns = now;
            }
        }

        /*
         * Un événement capteur réveille naturellement la boucle à environ
         * 200 Hz. Le délai de 25 ms n'est qu'un filet de sécurité pour UDP,
         * l'arrêt et la détection d'une pause du capteur : aucun polling à
         * haute fréquence n'a lieu entre deux véritables mesures.
         */
        SDL_Event waited_event;
        if (SDL_WaitEventTimeout(
                &waited_event,
                25
            )) {
            handle_runtime_event(
                &waited_event,
                &controller,
                socket_handle,
                &clients,
                server_id,
                &dsu_timeline,
                &total_packets,
                &telemetry
            );
        }
    }

    printf("\nArrêt propre de JoyConDSU.\n");

    close_controller(&controller);
    dsu_socket_close(socket_handle);
    dsu_socket_platform_cleanup();
    SDL_Quit();
    dsu_platform_cleanup();

    return EXIT_SUCCESS;
}
