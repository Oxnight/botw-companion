#ifndef JOYCON_DSU_PLATFORM_RUNTIME_H
#define JOYCON_DSU_PLATFORM_RUNTIME_H

#include <stdbool.h>
#include <stdint.h>

bool dsu_platform_install_stop_handler(void);
bool dsu_platform_stop_requested(void);
void dsu_platform_cleanup(void);
uint32_t dsu_platform_process_id(void);
const char *dsu_platform_name(void);

#endif