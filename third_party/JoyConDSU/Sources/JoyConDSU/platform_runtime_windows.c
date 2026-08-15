#include "platform_runtime.h"

#ifdef _WIN32

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

static volatile LONG stop_requested = 0;

static BOOL WINAPI handle_console_control(DWORD control_type)
{
    switch (control_type) {
    case CTRL_C_EVENT:
    case CTRL_BREAK_EVENT:
    case CTRL_CLOSE_EVENT:
    case CTRL_LOGOFF_EVENT:
    case CTRL_SHUTDOWN_EVENT:
        InterlockedExchange(&stop_requested, 1);
        return TRUE;
    default:
        return FALSE;
    }
}

bool dsu_platform_install_stop_handler(void)
{
    return SetConsoleCtrlHandler(handle_console_control, TRUE) != FALSE;
}

bool dsu_platform_stop_requested(void)
{
    return InterlockedCompareExchange(&stop_requested, 0, 0) != 0;
}

uint32_t dsu_platform_process_id(void)
{
    return (uint32_t)GetCurrentProcessId();
}

const char *dsu_platform_name(void)
{
    return "Windows";
}

#endif