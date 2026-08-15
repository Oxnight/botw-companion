#include "platform_runtime.h"

#ifdef _WIN32

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <wchar.h>

static volatile LONG stop_requested = 0;
static HANDLE stop_event = NULL;
static bool console_handler_installed = false;

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
    wchar_t event_name[96];
    const int written = swprintf(
        event_name,
        sizeof(event_name) / sizeof(event_name[0]),
        L"Local\\BOTWCompanion.JoyConDSU.Stop.%lu",
        (unsigned long)GetCurrentProcessId()
    );
    if (written <= 0) {
        return false;
    }
    console_handler_installed = SetConsoleCtrlHandler(
        handle_console_control,
        TRUE
    ) != FALSE;
    stop_event = CreateEventW(NULL, TRUE, FALSE, event_name);
    if (stop_event == NULL) {
        if (console_handler_installed) {
            (void)SetConsoleCtrlHandler(handle_console_control, FALSE);
            console_handler_installed = false;
        }
        return false;
    }
    return true;
}

bool dsu_platform_stop_requested(void)
{
    if (stop_event != NULL
        && WaitForSingleObject(stop_event, 0) == WAIT_OBJECT_0) {
        InterlockedExchange(&stop_requested, 1);
    }
    return InterlockedCompareExchange(&stop_requested, 0, 0) != 0;
}

void dsu_platform_cleanup(void)
{
    if (stop_event != NULL) {
        (void)CloseHandle(stop_event);
        stop_event = NULL;
    }
    if (console_handler_installed) {
        (void)SetConsoleCtrlHandler(handle_console_control, FALSE);
        console_handler_installed = false;
    }
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