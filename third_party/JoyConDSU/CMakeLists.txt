cmake_minimum_required(VERSION 3.26)

project(JoyConDSU
    VERSION 1.1.0
    DESCRIPTION "Reliable local DSU/CemuHook motion server for Nintendo Joy-Con"
    LANGUAGES C
)

set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

option(
    JOYCON_DSU_FETCH_SDL
    "Download the pinned SDL3 source when no packaged SDL3 is provided"
    OFF
)

if(JOYCON_DSU_FETCH_SDL)
    include(FetchContent)
    set(SDL_SHARED ON CACHE BOOL "" FORCE)
    set(SDL_STATIC OFF CACHE BOOL "" FORCE)
    set(SDL_TEST_LIBRARY OFF CACHE BOOL "" FORCE)
    set(SDL_TESTS OFF CACHE BOOL "" FORCE)
    set(SDL_EXAMPLES OFF CACHE BOOL "" FORCE)
    if(APPLE)
        # SDL has a native HIDAPI backend on macOS.  Do not auto-detect the
        # runner's Homebrew libusb: that would make the packaged dylib depend
        # on /opt/homebrew and break on a clean player's Mac.
        set(SDL_HIDAPI_LIBUSB OFF CACHE BOOL "" FORCE)
        set(SDL_HIDAPI_LIBUSB_SHARED OFF CACHE BOOL "" FORCE)
    endif()
    FetchContent_Declare(
        SDL3
        URL https://github.com/libsdl-org/SDL/releases/download/release-3.4.14/SDL3-3.4.14.tar.gz
        URL_HASH SHA256=30d4aa2b3037718142b32dffd4e72f917ebb6cc5227150e7bb9c45efb2153aeb
        DOWNLOAD_EXTRACT_TIMESTAMP TRUE
    )
    FetchContent_MakeAvailable(SDL3)
else()
    find_package(SDL3 REQUIRED CONFIG)
endif()

set(JOYCON_DSU_SOURCES
    Sources/JoyConDSU/main.c
    Sources/JoyConDSU/calibration.c
    Sources/JoyConDSU/dsu_clients.c
    Sources/JoyConDSU/dsu_protocol.c
    Sources/JoyConDSU/motion_pipeline.c
    Sources/JoyConDSU/telemetry.c
)

if(WIN32)
    list(APPEND JOYCON_DSU_SOURCES
        Sources/JoyConDSU/platform_socket_windows.c
        Sources/JoyConDSU/platform_runtime_windows.c
    )
else()
    list(APPEND JOYCON_DSU_SOURCES
        Sources/JoyConDSU/platform_socket_posix.c
        Sources/JoyConDSU/platform_runtime_posix.c
    )
endif()

add_executable(JoyConDSU ${JOYCON_DSU_SOURCES})

target_include_directories(JoyConDSU
    PRIVATE
        Sources/JoyConDSU
)

target_link_libraries(JoyConDSU PRIVATE SDL3::SDL3)

if(WIN32)
    target_compile_definitions(JoyConDSU PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)
    target_link_libraries(JoyConDSU PRIVATE Ws2_32)
    if(MSVC)
        set_property(
            TARGET JoyConDSU
            PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"
        )
        target_compile_options(JoyConDSU PRIVATE /W4 /permissive- /utf-8)
    endif()
    if(TARGET SDL3::SDL3-shared)
        add_custom_command(
            TARGET JoyConDSU POST_BUILD
            COMMAND "${CMAKE_COMMAND}" -E copy_if_different
                "$<TARGET_FILE:SDL3::SDL3-shared>"
                "$<TARGET_FILE_DIR:JoyConDSU>"
            VERBATIM
        )
    endif()
endif()

if(APPLE)
    target_compile_definitions(JoyConDSU PRIVATE _DARWIN_C_SOURCE)
endif()

if(CMAKE_C_COMPILER_ID MATCHES "AppleClang|Clang|GNU")
    target_compile_options(JoyConDSU PRIVATE
        -Wall
        -Wextra
        -Wpedantic
        -Wconversion
        -Wshadow
        -Wformat=2
    )
endif()

install(TARGETS JoyConDSU RUNTIME DESTINATION bin)
if(WIN32 AND TARGET SDL3::SDL3-shared)
    install(FILES "$<TARGET_FILE:SDL3::SDL3-shared>" DESTINATION bin)
endif()
