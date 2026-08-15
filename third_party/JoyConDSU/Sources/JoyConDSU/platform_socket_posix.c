#include "platform_socket.h"

#ifndef _WIN32

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <netinet/in.h>
#include <stdio.h>
#include <unistd.h>

bool dsu_socket_platform_init(void)
{
    return true;
}

void dsu_socket_platform_cleanup(void)
{
}

static bool set_nonblocking(DsuSocket socket_handle)
{
    const int flags = fcntl(socket_handle, F_GETFL, 0);
    return flags >= 0
        && fcntl(socket_handle, F_SETFL, flags | O_NONBLOCK) == 0;
}

DsuSocket dsu_socket_create_loopback_udp(uint16_t port)
{
    const DsuSocket socket_handle = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (socket_handle == DSU_INVALID_SOCKET) {
        dsu_socket_print_last_error("socket");
        return DSU_INVALID_SOCKET;
    }
    if (!set_nonblocking(socket_handle)) {
        dsu_socket_print_last_error("fcntl");
        dsu_socket_close(socket_handle);
        return DSU_INVALID_SOCKET;
    }
    struct sockaddr_in address = {0};
    address.sin_family = AF_INET;
    address.sin_port = htons(port);
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (bind(
            socket_handle,
            (const struct sockaddr *)&address,
            sizeof(address)
        ) != 0) {
        dsu_socket_print_last_error("bind");
        dsu_socket_close(socket_handle);
        return DSU_INVALID_SOCKET;
    }
    return socket_handle;
}

void dsu_socket_close(DsuSocket socket_handle)
{
    if (socket_handle != DSU_INVALID_SOCKET) {
        (void)close(socket_handle);
    }
}

DsuIoSize dsu_socket_receive(
    DsuSocket socket_handle,
    uint8_t *buffer,
    size_t buffer_size,
    DsuSocketAddress *sender,
    DsuSocklen *sender_len
)
{
    return recvfrom(
        socket_handle,
        buffer,
        buffer_size,
        0,
        (struct sockaddr *)sender,
        sender_len
    );
}

bool dsu_socket_last_error_would_block(void)
{
    return errno == EAGAIN || errno == EWOULDBLOCK;
}

bool dsu_socket_send(
    DsuSocket socket_handle,
    const uint8_t *packet,
    size_t packet_size,
    const DsuSocketAddress *address,
    DsuSocklen address_len
)
{
    const ssize_t sent = sendto(
        socket_handle,
        packet,
        packet_size,
        0,
        (const struct sockaddr *)address,
        address_len
    );
    return sent == (ssize_t)packet_size;
}

bool dsu_socket_address_ipv4_text(
    const DsuSocketAddress *address,
    char *buffer,
    size_t buffer_size
)
{
    if (address == NULL || address->ss_family != AF_INET
        || buffer == NULL || buffer_size == 0
        || buffer_size > (size_t)UINT_MAX) {
        return false;
    }
    const struct sockaddr_in *ipv4 = (const struct sockaddr_in *)address;
    return inet_ntop(
        AF_INET,
        &ipv4->sin_addr,
        buffer,
        (socklen_t)buffer_size
    ) != NULL;
}

uint16_t dsu_socket_address_port(const DsuSocketAddress *address)
{
    if (address == NULL || address->ss_family != AF_INET) {
        return 0;
    }
    const struct sockaddr_in *ipv4 = (const struct sockaddr_in *)address;
    return ntohs(ipv4->sin_port);
}

void dsu_socket_print_last_error(const char *operation)
{
    perror(operation);
}

#endif