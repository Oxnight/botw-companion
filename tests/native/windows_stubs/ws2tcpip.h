#ifndef TEST_WINDOWS_WS2TCPIP_H
#define TEST_WINDOWS_WS2TCPIP_H

#include "winsock2.h"

const char *InetNtopA(
    int family,
    const void *address,
    char *buffer,
    size_t buffer_size
);

#endif
