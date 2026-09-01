#ifndef TEST_WINDOWS_WINSOCK2_H
#define TEST_WINDOWS_WINSOCK2_H

#include <stddef.h>
#include <stdint.h>

typedef uintptr_t SOCKET;
typedef unsigned long u_long;
typedef unsigned long DWORD;
typedef unsigned short WORD;

typedef struct WSAData {
    WORD wVersion;
} WSADATA;

struct in_addr {
    uint32_t s_addr;
};

struct sockaddr {
    unsigned short sa_family;
    char sa_data[14];
};

struct sockaddr_in {
    short sin_family;
    uint16_t sin_port;
    struct in_addr sin_addr;
    char sin_zero[8];
};

struct sockaddr_storage {
    short ss_family;
    char padding[126];
};

#define AF_INET 2
#define SOCK_DGRAM 2
#define IPPROTO_UDP 17
#define INADDR_LOOPBACK 0x7f000001u
#define INVALID_SOCKET ((SOCKET)(~(SOCKET)0))
#define SOCKET_ERROR (-1)
#define FIONBIO 1L
#define WSAEINVAL 10022
#define WSAEWOULDBLOCK 10035
#define MAKEWORD(low, high) ((WORD)(((uint8_t)(low)) | ((WORD)((uint8_t)(high))) << 8))
#define LOBYTE(value) ((uint8_t)((value) & 0xffu))
#define HIBYTE(value) ((uint8_t)(((value) >> 8) & 0xffu))

int WSAStartup(WORD version, WSADATA *data);
int WSACleanup(void);
int WSAGetLastError(void);
void WSASetLastError(int error);
SOCKET socket(int family, int type, int protocol);
int ioctlsocket(SOCKET socket_handle, long command, u_long *argument);
int closesocket(SOCKET socket_handle);
int bind(SOCKET socket_handle, const struct sockaddr *address, int address_len);
int recvfrom(
    SOCKET socket_handle,
    char *buffer,
    int length,
    int flags,
    struct sockaddr *sender,
    int *sender_len
);
int sendto(
    SOCKET socket_handle,
    const char *buffer,
    int length,
    int flags,
    const struct sockaddr *destination,
    int destination_len
);
uint16_t htons(uint16_t value);
uint16_t ntohs(uint16_t value);
uint32_t htonl(uint32_t value);

#endif