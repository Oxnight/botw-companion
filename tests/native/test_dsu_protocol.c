#include "dsu_clients.h"
#include "dsu_protocol.h"

#include <arpa/inet.h>
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <string.h>
#include <zlib.h>

static void write_u16(uint8_t *packet, size_t offset, uint16_t value)
{
    packet[offset] = (uint8_t)value;
    packet[offset + 1] = (uint8_t)(value >> 8);
}

static void write_u32(uint8_t *packet, size_t offset, uint32_t value)
{
    for (size_t i = 0; i < 4; ++i) {
        packet[offset + i] = (uint8_t)(value >> (8u * i));
    }
}

static uint32_t crc_of(const uint8_t *packet, size_t size)
{
    uint8_t copy[128];
    assert(size <= sizeof(copy));
    memcpy(copy, packet, size);
    memset(copy + 8, 0, 4);
    return (uint32_t)crc32(0L, copy, (uInt)size);
}

static size_t client_request(
    uint8_t packet[64], uint32_t type, const uint8_t *payload, size_t payload_size
)
{
    const size_t size = 20 + payload_size;
    memset(packet, 0, 64);
    memcpy(packet, "DSUC", 4);
    write_u16(packet, 4, DSU_PROTOCOL_VERSION);
    write_u16(packet, 6, (uint16_t)(size - 16));
    write_u32(packet, 12, 0x42545743u);
    write_u32(packet, 16, type);
    if (payload_size > 0) {
        memcpy(packet + 20, payload, payload_size);
    }
    write_u32(packet, 8, crc_of(packet, size));
    return size;
}

static struct sockaddr_storage address(uint16_t port)
{
    struct sockaddr_storage storage = {0};
    struct sockaddr_in *ipv4 = (struct sockaddr_in *)&storage;
    ipv4->sin_family = AF_INET;
    ipv4->sin_port = htons(port);
    ipv4->sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    return storage;
}

static uint8_t hex_nibble(char value)
{
    if (value >= '0' && value <= '9') return (uint8_t)(value - '0');
    if (value >= 'a' && value <= 'f') return (uint8_t)(value - 'a' + 10);
    assert(false);
    return 0;
}

static void assert_packet_hex(
    const uint8_t *packet, size_t size, const char *expected_hex
)
{
    assert(strlen(expected_hex) == size * 2);
    for (size_t i = 0; i < size; ++i) {
        const uint8_t expected = (uint8_t)(
            (uint8_t)(hex_nibble(expected_hex[i * 2]) << 4)
            | hex_nibble(expected_hex[i * 2 + 1])
        );
        assert(packet[i] == expected);
    }
}

int main(void)
{
    const uint8_t mac[6] = {2, 0x4a, 0x43, 0x44, 0x53, 0x55};
    uint8_t packet[DSU_PACKET_DATA_SIZE];

    dsu_build_version_response(packet, 0x11223344u);
    assert(memcmp(packet, "DSUS", 4) == 0);
    assert(dsu_read_u16_le(packet, 4) == 1001u);
    assert(dsu_read_u16_le(packet, 6) == 6u);
    assert(dsu_read_u32_le(packet, 12) == 0x11223344u);
    assert(dsu_read_u32_le(packet, 16) == DSU_MSG_VERSION);
    assert(dsu_read_u16_le(packet, 20) == 1001u);
    assert(dsu_read_u32_le(packet, 8) == crc_of(packet, 22));
    assert_packet_hex(
        packet, 22,
        "44535553e90306003eb566f44433221100001000e903"
    );

    dsu_build_port_info_response(packet, 0x11223344u, 0, true, mac);
    assert(dsu_read_u16_le(packet, 6) == 16u);
    assert(packet[20] == 0 && packet[21] == 2 && packet[22] == 2);
    assert(packet[23] == 2 && memcmp(packet + 24, mac, 6) == 0);
    assert(packet[31] == 0);
    assert(dsu_read_u32_le(packet, 8) == crc_of(packet, 32));
    assert_packet_hex(
        packet, 32,
        "44535553e903100095068d21443322110100100000020202024a434453550000"
    );

    assert(dsu_build_controller_data(
        packet, 0x11223344u, 7u, mac, 123456u,
        (DsuVec3){1.0f, -2.0f, 3.0f},
        (DsuVec3){4.0f, -5.0f, 6.0f}
    ));
    assert(dsu_read_u16_le(packet, 6) == 84u);
    assert(dsu_read_u32_le(packet, 32) == 7u);
    assert(packet[40] == 128 && packet[41] == 128
        && packet[42] == 128 && packet[43] == 128);
    assert(dsu_read_u32_le(packet, 8) == crc_of(packet, 100));
    assert_packet_hex(
        packet, 100,
        "44535553e9035400a9cd616f443322110200100000020202024a434453550001"
        "0700000000000000808080800000000000000000000000000000000000000000"
        "0000000040e20100000000000000803f000000c000004040000080400000a0c0"
        "0000c040"
    );
    assert(!dsu_build_controller_data(
        packet, 1u, 0u, mac, 1u,
        (DsuVec3){NAN, 0.0f, 0.0f}, (DsuVec3){0.0f, 0.0f, 0.0f}
    ));

    uint8_t request[64];
    size_t size = client_request(request, DSU_MSG_VERSION, NULL, 0);
    DsuParsedPacket parsed = dsu_parse_client_packet(request, size);
    assert(parsed.valid && parsed.crc_valid);
    assert(dsu_request_shape_valid(request, &parsed));
    request[8] ^= 1u;
    parsed = dsu_parse_client_packet(request, size);
    assert(parsed.valid && !parsed.crc_valid);
    assert(dsu_request_shape_valid(request, &parsed));

    const uint8_t ports_payload[5] = {1, 0, 0, 0, 0};
    size = client_request(request, DSU_MSG_PORTS, ports_payload, 5);
    parsed = dsu_parse_client_packet(request, size);
    assert(dsu_request_shape_valid(request, &parsed));
    request[20] = 2;
    parsed = dsu_parse_client_packet(request, size);
    assert(!dsu_request_shape_valid(request, &parsed));

    uint8_t subscription[8] = {1, 0, 0, 0, 0, 0, 0, 0};
    size = client_request(request, DSU_MSG_DATA, subscription, 8);
    parsed = dsu_parse_client_packet(request, size);
    assert(dsu_request_shape_valid(request, &parsed));
    assert(dsu_subscription_matches(request, size, 0, mac));
    request[21] = 1;
    assert(!dsu_subscription_matches(request, size, 0, mac));
    request[20] = 4;
    parsed = dsu_parse_client_packet(request, size);
    assert(!dsu_request_shape_valid(request, &parsed));

    DsuClientRegistry registry;
    dsu_clients_reset(&registry);
    struct sockaddr_storage first = address(40000);
    bool is_new = false;
    DsuClient *client = dsu_clients_subscribe(
        &registry, &first, sizeof(struct sockaddr_in), 100u, &is_new
    );
    assert(client != NULL && is_new && client->packet_number == 0);
    client->packet_number++;
    assert(dsu_clients_subscribe(
        &registry, &first, sizeof(struct sockaddr_in), 200u, &is_new
    ) == client);
    assert(!is_new && client->packet_number == 1);
    assert(dsu_clients_expire(
        &registry, 5000000200ULL, 5000000000ULL
    ) == 0);
    assert(dsu_clients_active_count(&registry) == 1);
    assert(dsu_clients_expire(
        &registry, 5000000201ULL, 5000000000ULL
    ) == 1);
    assert(dsu_clients_active_count(&registry) == 0);

    for (uint16_t i = 0; i < DSU_MAX_CLIENTS; ++i) {
        struct sockaddr_storage item = address((uint16_t)(41000u + i));
        assert(dsu_clients_subscribe(
            &registry, &item, sizeof(struct sockaddr_in), 1000u, NULL
        ) != NULL);
    }
    struct sockaddr_storage excess = address(42000);
    assert(dsu_clients_subscribe(
        &registry, &excess, sizeof(struct sockaddr_in), 1000u, NULL
    ) == NULL);

    return 0;
}