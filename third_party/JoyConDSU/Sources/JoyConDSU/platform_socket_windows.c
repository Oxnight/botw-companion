#include "platform_socket.h"

#ifdef _WIN32

#include <limits.h>
#include <stdio.h>
#include <string.h>

bool dsu_socket_platform_init(void)
{
    WSADATA data;
    const int status = WSAStartup(MAKEWORD(2, 2), &data);
    if (status != 0) {
        fprintf(stderr, "WSAStartup a échoué : %d\n", status);
        return false;
    }
    if (LOBYTE(data.wVersion) != 2 || HIBYTE(data.wVersion) != 2) {
        fprintf(stderr, "Winsock 2.2 n'est pas disponible.\n");
        WSACleanup();
        return false;
    }
    return true;
}

void dsu_socket_platform_cleanup(void)
{
    (void)WSACleanup();
}

static bool set_nonblocking(DsuSocket socket_handle)
{
    u_long enabled = 1;
    return ioctlsocket(socket_handle, FIONBIO, &enabled) == 0;
}

DsuSocket dsu_socket_create_loopback_udp(uint16_t port)
{
    const DsuSocket socket_handle = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (socket_handle == DSU_INVALID_SOCKET) {
        dsu_socket_print_last_error("socket");
        return DSU_INVALID_SOCKET;
    }
    if (!set_nonblocking(socket_handle)) {
        dsu_socket_print_last_error("ioctlsocket");
        dsu_socket_close(socket_handle);
        return DSU_INVALID_SOCKET;
    }
    struct sockaddr_in address;
    memset(&address, 0, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_port = htons(port);
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (bind(
            socket_handle,
            (const struct sockaddr *)&address,
            (int)sizeof(address)
        ) == SOCKET_ERROR) {
        dsu_socket_print_last_error("bind");
        dsu_socket_close(socket_handle);
        return DSU_INVALID_SOCKET;
    }
    return socket_handle;
}

void dsu_socket_close(DsuSocket socket_handle)
{
    if (socket_handle != DSU_INVALID_SOCKET) {
        (void)closesocket(socket_handle);
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
    if (buffer_size > (size_t)INT_MAX) {
        WSASetLastError(WSAEINVAL);
        return SOCKET_ERROR;
    }
    return recvfrom(
        socket_handle,
        (char *)buffer,
        (int)buffer_size,
        0,
        (struct sockaddr *)sender,
        sender_len
    );
}

bool dsu_socket_last_error_would_block(void)
{
    return WSAGetLastError() == WSAEWOULDBLOCK;
}

bool dsu_socket_send(
    DsuSocket socket_handle,
    const uint8_t *packet,
    size_t packet_size,
    const DsuSocketAddress *address,
    DsuSocklen address_len
)
{
    if (packet_size > (size_t)INT_MAX) {
        WSASetLastError(WSAEINVAL);
        return false;
    }
    const int sent = sendto(
        socket_handle,
        (const char *)packet,
        (int)packet_size,
        0,
        (const struct sockaddr *)address,
        address_len
    );
    return sent == (int)packet_size;
}

bool dsu_socket_address_ipv4_text(
    const DsuSocketAddress *address,
    char *buffer,
    size_t buffer_size
)
{
    if (address == NULL || address->ss_family != AF_INET
        || buffer == NULL || buffer_size == 0) {
        return false;
    }
    const struct sockaddr_in *ipv4 = (const struct sockaddr_in *)address;
    return InetNtopA(AF_INET, (const void *)&ipv4->sin_addr, buffer, buffer_size)
        != NULL;
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
    fprintf(stderr, "%s a échoué (Winsock %d).\n", operation, WSAGetLastError());
}

#endif