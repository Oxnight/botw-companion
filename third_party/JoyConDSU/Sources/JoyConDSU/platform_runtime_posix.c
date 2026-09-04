#include "platform_runtime.h"

#ifndef _WIN32

#include <signal.h>
#include <unistd.h>

static volatile sig_atomic_t stop_requested = 0;

static void handle_signal(int signal_number)
{
    (void)signal_number;
    stop_requested = 1;
}

bool dsu_platform_install_stop_handler(void)
{
    return signal(SIGINT, handle_signal) != SIG_ERR
        && signal(SIGTERM, handle_signal) != SIG_ERR;
}

bool dsu_platform_stop_requested(void)
{
    return stop_requested != 0;
}

void dsu_platform_cleanup(void)
{
}

uint32_t dsu_platform_process_id(void)
{
    return (uint32_t)getpid();
}

const char *dsu_platform_name(void)
{
#ifdef __APPLE__
    return "macOS";
#else
    return "POSIX";
#endif
}

#endif
