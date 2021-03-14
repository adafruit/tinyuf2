#ifndef GHOSTFAT_TEST_CONFIG_H
#define GHOSTFAT_TEST_CONFIG_H
#ifdef __cplusplus
 extern "C" {
#endif

#include <stdint.h>

// From board_api.h
#define BOARD_FLASH_APP_START  0
#define TINYUF2_LED 0
#define TINYUF2_DFU_DOUBLE_TAP      0
#define TINYUF2_DISPLAY 0

#define FLASH_SIZE_4MiB  (4u * 1024u * 1024u);

#define GHOSTFAT_SELF_TEST_MODE 1
int test_main(void);

#include "board.h"

#ifdef __cplusplus
 }
#endif
#endif  // GHOSTFAT_TEST_CONFIG_H