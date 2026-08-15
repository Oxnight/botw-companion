#ifndef JOYCON_DSU_PROTOCOL_H
#define JOYCON_DSU_PROTOCOL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    DSU_PROTOCOL_VERSION = 1001,
    DSU_DEFAULT_PORT = 26760,
    DSU_PACKET_VERSION_SIZE = 22,
    DSU_PACKET_PORT_INFO_SIZE = 32,
    DSU_PACKET_DATA_SIZE = 100,
};

enum {
    DSU_MSG_VERSION = 0x100000,
    DSU_MSG_PORTS   = 0x100001,
    DSU_MSG_DATA    = 0x100002,
};

typedef struct {
    float x;
    float y;
    float z;
} DsuVec3;

typedef struct {
    bool valid;
    bool crc_valid;
    size_t effective_size;
    uint16_t protocol_version;
    uint32_t sender_id;
    uint32_t message_type;
} DsuParsedPacket;

uint16_t dsu_read_u16_le(const uint8_t *buffer, size_t offset);
uint32_t dsu_read_u32_le(const uint8_t *buffer, size_t offset);

DsuParsedPacket dsu_parse_client_packet(
    const uint8_t *packet,
    size_t received_size
);

void dsu_build_version_response(
    uint8_t packet[DSU_PACKET_VERSION_SIZE],
    uint32_t server_id
);

void dsu_build_port_info_response(
    uint8_t packet[DSU_PACKET_PORT_INFO_SIZE],
    uint32_t server_id,
    uint8_t slot,
    bool connected,
    const uint8_t mac[6]
);

bool dsu_build_controller_data(
    uint8_t packet[DSU_PACKET_DATA_SIZE],
    uint32_t server_id,
    uint32_t packet_number,
    const uint8_t mac[6],
    uint64_t timestamp_us,
    DsuVec3 accel_g,
    DsuVec3 gyro_deg_s
);

bool dsu_request_shape_valid(
    const uint8_t *packet,
    const DsuParsedPacket *parsed
);

bool dsu_motion_values_finite(DsuVec3 accel_g, DsuVec3 gyro_deg_s);

bool dsu_subscription_matches(
    const uint8_t *packet,
    size_t effective_size,
    uint8_t served_slot,
    const uint8_t served_mac[6]
);

#ifdef __cplusplus
}
#endif

#endif