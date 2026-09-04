#ifndef TEST_WINDOWS_H
#define TEST_WINDOWS_H

#include <stddef.h>
#include <stdint.h>

typedef int BOOL;
typedef unsigned long DWORD;
typedef long LONG;
typedef void *HANDLE;

#define WINAPI
#define TRUE 1
#define FALSE 0
#define CTRL_C_EVENT 0
#define CTRL_BREAK_EVENT 1
#define CTRL_CLOSE_EVENT 2
#define CTRL_LOGOFF_EVENT 5
#define CTRL_SHUTDOWN_EVENT 6
#define WAIT_OBJECT_0 0

typedef BOOL (WINAPI *PHANDLER_ROUTINE)(DWORD control_type);

BOOL SetConsoleCtrlHandler(PHANDLER_ROUTINE handler, BOOL add);
LONG InterlockedExchange(volatile LONG *target, LONG value);
LONG InterlockedCompareExchange(
    volatile LONG *destination,
    LONG exchange,
    LONG comparison
);
DWORD GetCurrentProcessId(void);
HANDLE CreateEventW(
    void *event_attributes,
    BOOL manual_reset,
    BOOL initial_state,
    const wchar_t *name
);
DWORD WaitForSingleObject(HANDLE handle, DWORD milliseconds);
BOOL CloseHandle(HANDLE handle);

#endif
