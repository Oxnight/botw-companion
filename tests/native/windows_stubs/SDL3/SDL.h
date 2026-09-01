#ifndef TEST_WINDOWS_SDL_H
#define TEST_WINDOWS_SDL_H

#include <stdbool.h>
#include <stdint.h>

typedef int32_t SDL_JoystickID;
typedef int32_t SDL_GamepadType;
typedef int32_t Sint32;
typedef struct SDL_Gamepad SDL_Gamepad;

typedef struct SDL_GamepadDeviceEvent {
    uint32_t type;
    uint64_t timestamp;
    SDL_JoystickID which;
} SDL_GamepadDeviceEvent;

typedef struct SDL_GamepadSensorEvent {
    uint32_t type;
    uint32_t reserved;
    uint64_t timestamp;
    SDL_JoystickID which;
    int32_t sensor;
    float data[3];
    uint64_t sensor_timestamp;
} SDL_GamepadSensorEvent;

typedef union SDL_Event {
    uint32_t type;
    SDL_GamepadDeviceEvent gdevice;
    SDL_GamepadSensorEvent gsensor;
} SDL_Event;

#define SDL_INIT_GAMEPAD 0x00002000u
#define SDL_INIT_SENSOR 0x00008000u
#define SDL_EVENT_GAMEPAD_REMOVED 0x653u
#define SDL_EVENT_GAMEPAD_SENSOR_UPDATE 0x659u
#define SDL_SENSOR_ACCEL 1
#define SDL_SENSOR_GYRO 2
#define SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_PRO 11
#define SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_JOYCON_LEFT 12
#define SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_JOYCON_RIGHT 13
#define SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_JOYCON_PAIR 14
#define SDL_HINT_JOYSTICK_HIDAPI_JOY_CONS "SDL_JOYSTICK_HIDAPI_JOY_CONS"
#define SDL_HINT_JOYSTICK_HIDAPI_COMBINE_JOY_CONS \
    "SDL_JOYSTICK_HIDAPI_COMBINE_JOY_CONS"

bool SDL_SetHint(const char *name, const char *value);
bool SDL_Init(uint32_t flags);
void SDL_Quit(void);
uint64_t SDL_GetTicksNS(void);
const char *SDL_GetError(void);
SDL_JoystickID *SDL_GetGamepads(int *count);
void SDL_free(void *memory);
SDL_Gamepad *SDL_OpenGamepad(SDL_JoystickID instance_id);
void SDL_CloseGamepad(SDL_Gamepad *gamepad);
SDL_GamepadType SDL_GetGamepadType(SDL_Gamepad *gamepad);
bool SDL_GamepadHasSensor(SDL_Gamepad *gamepad, int32_t sensor);
bool SDL_SetGamepadSensorEnabled(
    SDL_Gamepad *gamepad,
    int32_t sensor,
    bool enabled
);
float SDL_GetGamepadSensorDataRate(SDL_Gamepad *gamepad, int32_t sensor);
const char *SDL_GetGamepadName(SDL_Gamepad *gamepad);
const char *SDL_GetGamepadPath(SDL_Gamepad *gamepad);
uint16_t SDL_GetGamepadVendor(SDL_Gamepad *gamepad);
uint16_t SDL_GetGamepadProduct(SDL_Gamepad *gamepad);
const char *SDL_GetGamepadStringForType(SDL_GamepadType type);
bool SDL_GamepadConnected(SDL_Gamepad *gamepad);
bool SDL_PollEvent(SDL_Event *event);
bool SDL_WaitEventTimeout(SDL_Event *event, int timeout_ms);
void SDL_FlushEvents(uint32_t min_type, uint32_t max_type);
void SDL_Delay(uint32_t milliseconds);

#endif