// SPDX-License-Identifier: MIT
#pragma once
#include "ch32v4x7.h"
#include "board.h"

#define TINYUF2_LED              1
#define TINYUF2_DBL_TAP_DFU      1
#define TINYUF2_DBL_TAP_REG      BKP->DATAR10
#define TINYUF2_DBL_TAP_REG_SIZE 16
#define BOARD_FLASH_SIZE         (512u * 1024u)
#define BOARD_FLASH_APP_START    0x8000u
#define BOARD_FLASH_ADDR_ZERO    BOARD_FLASH_APP_START
#define CFG_UF2_FLASH_SIZE       BOARD_FLASH_SIZE
#define BOARD_FLASH_PAGE_SIZE    4096u
