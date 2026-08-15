#include "dsu_protocol.h"

#include <math.h>
#include <string.h>

enum {
    DSU_HEADER_SIZE = 16,
    DSU_MESSAGE_HEADER_SIZE = 20,
    DSU_CONTROLLER_INFO_SIZE = 11,
};

static void write_u16_le(uint8_t *buffer, size_t offset, uint16_t value)
{
    buffer[offset] = (uint8_t)(value & 0xffu);
    buffer[offset + 1] = (uint8_t)((value >> 8) & 0xffu);
}

static void write_u32_le(uint8_t *buffer, size_t offset, uint32_t value)
{
    buffer[offset] = (uint8_t)(value & 0xffu);
    buffer[offset + 1] = (uint8_t)((value >> 8) & 0xffu);
    buffer[offset + 2] = (uint8_t)((value >> 16) & 0xffu);
    buffer[offset + 3] = (uint8_t)((value >> 24) & 0xffu);
}

static void write_u64_le(uint8_t *buffer, size_t offset, uint64_t value)
{
    for (size_t i = 0; i < 8; ++i) {
        buffer[offset + i] = (uint8_t)((value >> (8u * i)) & 0xffu);
    }
}

static void write_float_le(uint8_t *buffer, size_t offset, float value)
{
    uint32_t bits = 0;
    _Static_assert(sizeof(bits) == sizeof(value), "float must be 32-bit");
    memcpy(&bits, &value, sizeof(bits));
    write_u32_le(buffer, offset, bits);
}

uint16_t dsu_read_u16_le(const uint8_t *buffer, size_t offset)
{
    return (uint16_t)(
        (uint16_t)buffer[offset]
        | ((uint16_t)buffer[offset + 1] << 8)
    );
}

uint32_t dsu_read_u32_le(const uint8_t *buffer, size_t offset)
{
    return
        (uint32_t)buffer[offset]
        | ((uint32_t)buffer[offset + 1] << 8)
        | ((uint32_t)buffer[offset + 2] << 16)
        | ((uint32_t)buffer[offset + 3] << 24);
}

static uint32_t packet_crc32(const uint8_t *packet, size_t size)
{
    uint32_t crc = 0xffffffffu;
    for (size_t i = 0; i < size; ++i) {
        crc ^= packet[i];
        for (unsigned bit = 0; bit < 8; ++bit) {
            const uint32_t mask = 0u - (crc & 1u);
            crc = (crc >> 1) ^ (0xedb88320u & mask);
        }
    }
    return ~crc;
}

static void finish_server_packet(
    uint8_t *packet,
    size_t packet_size,
    uint32_t server_id,
    uint32_t message_type
)
{
    memcpy(packet, "DSUS", 4);

    write_u16_le(packet, 4, DSU_PROTOCOL_VERSION);
    write_u16_le(packet, 6, (uint16_t)(packet_size - DSU_HEADER_SIZE));
    write_u32_le(packet, 8, 0u);
    write_u32_le(packet, 12, server_id);
    write_u32_le(packet, 16, message_type);

    write_u32_le(packet, 8, packet_crc32(packet, packet_size));
}

DsuParsedPacket dsu_parse_client_packet(
    const uint8_t *packet,
    size_t received_size
)
{
    DsuParsedPacket result = {0};

    if (packet == NULL || received_size < DSU_MESSAGE_HEADER_SIZE) {
        return result;
    }

    if (memcmp(packet, "DSUC", 4) != 0) {
        return result;
    }

    const uint16_t version = dsu_read_u16_le(packet, 4);
    if (version > DSU_PROTOCOL_VERSION) {
        return result;
    }

    const uint16_t payload_length = dsu_read_u16_le(packet, 6);
    const size_t declared_total = DSU_HEADER_SIZE + (size_t)payload_length;

    if (declared_total < DSU_MESSAGE_HEADER_SIZE || received_size < declared_total) {
        return result;
    }

    /*
     * The DSU reference says to truncate packets longer than the declared
     * length. CRC must therefore be calculated over the declared packet size.
     */
    uint8_t copy[1024];

    if (declared_total > sizeof(copy)) {
        return result;
    }

    memcpy(copy, packet, declared_total);

    const uint32_t received_crc = dsu_read_u32_le(copy, 8);
    write_u32_le(copy, 8, 0u);

    result.valid = true;
    result.crc_valid = (received_crc == packet_crc32(copy, declared_total));
    result.effective_size = declared_total;
    result.protocol_version = version;
    result.sender_id = dsu_read_u32_le(packet, 12);
    result.message_type = dsu_read_u32_le(packet, 16);

    return result;
}

static void fill_controller_info(
    uint8_t *payload,
    uint8_t slot,
    bool connected,
    const uint8_t mac[6]
)
{
    memset(payload, 0, DSU_CONTROLLER_INFO_SIZE);
    payload[0] = slot;

    if (!connected) {
        return;
    }

    payload[1] = 2; /* connected */
    payload[2] = 2; /* full gyro */
    payload[3] = 2; /* Bluetooth */
    memcpy(payload + 4, mac, 6);
    payload[10] = 0x00; /* battery unknown / not applicable */
}

void dsu_build_version_response(
    uint8_t packet[DSU_PACKET_VERSION_SIZE],
    uint32_t server_id
)
{
    memset(packet, 0, DSU_PACKET_VERSION_SIZE);
    write_u16_le(packet, 20, DSU_PROTOCOL_VERSION);
    finish_server_packet(packet, DSU_PACKET_VERSION_SIZE, server_id, DSU_MSG_VERSION);
}

void dsu_build_port_info_response(
    uint8_t packet[DSU_PACKET_PORT_INFO_SIZE],
    uint32_t server_id,
    uint8_t slot,
    bool connected,
    const uint8_t mac[6]
)
{
    memset(packet, 0, DSU_PACKET_PORT_INFO_SIZE);
    fill_controller_info(packet + 20, slot, connected, mac);
    packet[31] = 0;
    finish_server_packet(packet, DSU_PACKET_PORT_INFO_SIZE, server_id, DSU_MSG_PORTS);
}

bool dsu_build_controller_data(
    uint8_t packet[DSU_PACKET_DATA_SIZE],
    uint32_t server_id,
    uint32_t packet_number,
    const uint8_t mac[6],
    uint64_t timestamp_us,
    DsuVec3 accel_g,
    DsuVec3 gyro_deg_s
)
{
    if (packet == NULL || mac == NULL
        || !dsu_motion_values_finite(accel_g, gyro_deg_s)) {
        return false;
    }
    memset(packet, 0, DSU_PACKET_DATA_SIZE);

    uint8_t *payload = packet + 20;
    fill_controller_info(payload, 0, true, mac);

    payload[11] = 1;
    write_u32_le(payload, 12, packet_number);

    /* Buttons released, sticks neutral. */
    payload[20] = 128;
    payload[21] = 128;
    payload[22] = 128;
    payload[23] = 128;

    write_u64_le(payload, 48, timestamp_us);

    write_float_le(payload, 56, accel_g.x);
    write_float_le(payload, 60, accel_g.y);
    write_float_le(payload, 64, accel_g.z);

    write_float_le(payload, 68, gyro_deg_s.x);
    write_float_le(payload, 72, gyro_deg_s.y);
    write_float_le(payload, 76, gyro_deg_s.z);

    finish_server_packet(packet, DSU_PACKET_DATA_SIZE, server_id, DSU_MSG_DATA);
    return true;
}

bool dsu_motion_values_finite(DsuVec3 accel_g, DsuVec3 gyro_deg_s)
{
    return isfinite(accel_g.x) && isfinite(accel_g.y) && isfinite(accel_g.z)
        && isfinite(gyro_deg_s.x) && isfinite(gyro_deg_s.y)
        && isfinite(gyro_deg_s.z);
}

bool dsu_request_shape_valid(
    const uint8_t *packet,
    const DsuParsedPacket *parsed
)
{
    if (packet == NULL || parsed == NULL || !parsed->valid) {
        return false;
    }
    if (parsed->message_type == DSU_MSG_VERSION) {
        return parsed->effective_size == 20u;
    }
    if (parsed->message_type == DSU_MSG_PORTS) {
        if (parsed->effective_size < 24u) {
            return false;
        }
        const int32_t count = (int32_t)dsu_read_u32_le(packet, 20);
        return count >= 0 && count <= 4
            && parsed->effective_size == 24u + (size_t)count;
    }
    if (parsed->message_type == DSU_MSG_DATA) {
        if (parsed->effective_size != 28u) {
            return false;
        }
        const uint8_t flags = packet[20];
        return (flags & (uint8_t)~0x03u) == 0u;
    }
    return false;
}

bool dsu_subscription_matches(
    const uint8_t *packet,
    size_t effective_size,
    uint8_t served_slot,
    const uint8_t served_mac[6]
)
{
    if (packet == NULL || effective_size < 28) {
        return false;
    }

    const uint8_t flags = packet[20];

    if ((flags & (uint8_t)~0x03u) != 0u) {
        return false;
    }

    if (flags == 0u) {
        return true;
    }

    if ((flags & 0x01u) != 0u && packet[21] != served_slot) {
        return false;
    }

    if ((flags & 0x02u) != 0u && memcmp(packet + 22, served_mac, 6) != 0) {
        return false;
    }

    return true;
}