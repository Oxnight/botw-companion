#include "dsu_clients.h"

#include <string.h>

static bool same_address(
    const DsuSocketAddress *left,
    const DsuSocketAddress *right
)
{
    if (left->ss_family != AF_INET || right->ss_family != AF_INET) {
        return false;
    }
    const struct sockaddr_in *a = (const struct sockaddr_in *)left;
    const struct sockaddr_in *b = (const struct sockaddr_in *)right;
    return a->sin_addr.s_addr == b->sin_addr.s_addr
        && a->sin_port == b->sin_port;
}

void dsu_clients_reset(DsuClientRegistry *registry)
{
    if (registry != NULL) {
        memset(registry, 0, sizeof(*registry));
    }
}

DsuClient *dsu_clients_subscribe(
    DsuClientRegistry *registry,
    const DsuSocketAddress *address,
    DsuSocklen address_len,
    uint64_t now_ns,
    bool *is_new
)
{
    if (registry == NULL || address == NULL || address->ss_family != AF_INET
        || now_ns == 0) {
        return NULL;
    }
    for (size_t i = 0; i < DSU_MAX_CLIENTS; ++i) {
        DsuClient *client = &registry->entries[i];
        if (client->active && same_address(&client->address, address)) {
            client->last_subscription_ns = now_ns;
            if (is_new != NULL) {
                *is_new = false;
            }
            return client;
        }
    }
    for (size_t i = 0; i < DSU_MAX_CLIENTS; ++i) {
        DsuClient *client = &registry->entries[i];
        if (!client->active) {
            memset(client, 0, sizeof(*client));
            client->active = true;
            client->address = *address;
            client->address_len = address_len;
            client->last_subscription_ns = now_ns;
            if (is_new != NULL) {
                *is_new = true;
            }
            return client;
        }
    }
    return NULL;
}

size_t dsu_clients_expire(
    DsuClientRegistry *registry,
    uint64_t now_ns,
    uint64_t timeout_ns
)
{
    if (registry == NULL) {
        return 0;
    }
    size_t expired = 0;
    for (size_t i = 0; i < DSU_MAX_CLIENTS; ++i) {
        DsuClient *client = &registry->entries[i];
        if (client->active
            && (now_ns < client->last_subscription_ns
                || now_ns - client->last_subscription_ns > timeout_ns)) {
            memset(client, 0, sizeof(*client));
            expired += 1;
        }
    }
    return expired;
}

size_t dsu_clients_active_count(const DsuClientRegistry *registry)
{
    if (registry == NULL) {
        return 0;
    }
    size_t count = 0;
    for (size_t i = 0; i < DSU_MAX_CLIENTS; ++i) {
        count += registry->entries[i].active ? 1u : 0u;
    }
    return count;
}
