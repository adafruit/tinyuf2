#ifndef GHOSTFAT_TEST_CONFIG_H
#define GHOSTFAT_TEST_CONFIG_H

#ifdef __cplusplus
 extern "C" {
#endif

#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include "uf2.h"
#include "board.h"

// From board_api.h
#define BOARD_FLASH_APP_START  0

// call records of the board_flash_write() and board_flash_flush() stubs
extern uint32_t test_flash_write_count;
extern uint32_t test_flash_write_addr;
extern uint32_t test_flash_write_len;
extern uint8_t  test_flash_write_data[476]; // payload of the last write, UF2's data field at most
extern uint32_t test_flash_flush_count;

#ifdef __cplusplus
 }
#endif
#endif  // GHOSTFAT_TEST_CONFIG_H
