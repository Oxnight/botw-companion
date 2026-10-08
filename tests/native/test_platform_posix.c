#include "platform_runtime.h"
#include "platform_socket.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

int main(void)
{
    assert(dsu_platform_install_stop_handler());
    assert(!dsu_platform_stop_requested());
    assert(dsu_platform_process_id() > 0);
    assert(strlen(dsu_platform_name()) > 0);

    assert(dsu_socket_platform_init());
    DsuSocket socket_handle = dsu_socket_create_loopback_udp(0);
    assert(socket_handle != DSU_INVALID_SOCKET);

    uint8_t buffer[16] = {0};
    DsuSocketAddress sender = {0};
    DsuSocklen sender_len = (DsuSocklen)sizeof(sender);
    assert(dsu_socket_receive(
        socket_handle,
        buffer,
        sizeof(buffer),
        &sender,
        &sender_len
    ) < 0);
    assert(dsu_socket_last_error_would_block());

    dsu_socket_close(socket_handle);
    dsu_socket_platform_cleanup();
    dsu_platform_cleanup();
    return 0;
}
