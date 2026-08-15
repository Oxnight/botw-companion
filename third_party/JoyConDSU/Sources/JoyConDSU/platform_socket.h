#ifndef JOYCON_DSU_PLATFORM_SOCKET_H
#define JOYCON_DSU_PLATFORM_SOCKET_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
typedef SOCKET DsuSocket;
typedef int DsuSocklen;
typedef int DsuIoSize;
#define DSU_INVALID_SOCKET INVALID_SOCKET
#else
#include <netinet/in.h>
#include <sys/socket.h>
typedef int DsuSocket;
typedef socklen_t DsuSocklen;
typedef ssize_t DsuIoSize;
#define DSU_INVALID_SOCKET (-1)
#endif

typedef struct sockaddr_storage DsuSocketAddress;

bool dsu_socket_platform_init(void);
void dsu_socket_platform_cleanup(void);
DsuSocket dsu_socket_create_loopback_udp(uint16_t port);
void dsu_socket_close(DsuSocket socket_handle);
DsuIoSize dsu_socket_receive(
    DsuSocket socket_handle,
    uint8_t *buffer,
    size_t buffer_size,
    DsuSocketAddress *sender,
    DsuSocklen *sender_len
);
bool dsu_socket_last_error_would_block(void);
bool dsu_socket_send(
    DsuSocket socket_handle,
    const uint8_t *packet,
    size_t packet_size,
    const DsuSocketAddress *address,
    DsuSocklen address_len
);
bool dsu_socket_address_ipv4_text(
    const DsuSocketAddress *address,
    char *buffer,
    size_t buffer_size
);
uint16_t dsu_socket_address_port(const DsuSocketAddress *address);
void dsu_socket_print_last_error(const char *operation);

#endif