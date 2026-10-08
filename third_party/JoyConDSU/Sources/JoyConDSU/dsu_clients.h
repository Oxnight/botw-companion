#ifndef JOYCON_DSU_CLIENTS_H
#define JOYCON_DSU_CLIENTS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "platform_socket.h"

enum { DSU_MAX_CLIENTS = 8 };

typedef struct {
    bool active;
    DsuSocketAddress address;
    DsuSocklen address_len;
    uint64_t last_subscription_ns;
    uint32_t packet_number;
} DsuClient;

typedef struct {
    DsuClient entries[DSU_MAX_CLIENTS];
} DsuClientRegistry;

void dsu_clients_reset(DsuClientRegistry *registry);
DsuClient *dsu_clients_subscribe(
    DsuClientRegistry *registry,
    const DsuSocketAddress *address,
    DsuSocklen address_len,
    uint64_t now_ns,
    bool *is_new
);
size_t dsu_clients_expire(
    DsuClientRegistry *registry,
    uint64_t now_ns,
    uint64_t timeout_ns
);
size_t dsu_clients_active_count(const DsuClientRegistry *registry);

#endif
