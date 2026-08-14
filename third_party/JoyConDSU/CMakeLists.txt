cmake_minimum_required(VERSION 3.26)

project(JoyConDSU
    VERSION 1.0.0
    DESCRIPTION "Reliable local DSU/CemuHook motion server for Nintendo Joy-Con on macOS"
    LANGUAGES C
)

set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

find_package(SDL3 REQUIRED CONFIG)
find_package(ZLIB REQUIRED)

add_executable(JoyConDSU
    Sources/JoyConDSU/main.c
    Sources/JoyConDSU/calibration.c
    Sources/JoyConDSU/dsu_clients.c
    Sources/JoyConDSU/dsu_protocol.c
    Sources/JoyConDSU/motion_pipeline.c
    Sources/JoyConDSU/telemetry.c
)

target_include_directories(JoyConDSU
    PRIVATE
        Sources/JoyConDSU
)

target_link_libraries(JoyConDSU
    PRIVATE
        SDL3::SDL3
        ZLIB::ZLIB
)

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