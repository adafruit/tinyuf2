/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2025 Brent Kowal, Analog Devices, Inc
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#ifndef BOARDS_H_
#define BOARDS_H_

#ifdef __cplusplus
 extern "C" {
#endif

#include "board.h"

#if __has_include("mcr_regs.h")
#include "mcr_regs.h"
#endif

#if defined(MAX32650)
#define BOARD_FLASH_ADDR_ZERO   MXC_FLASH_MEM_BASE
#define BOARD_FLASH_SIZE        MXC_FLASH_MEM_SIZE
#define BOARD_FLASH_PAGE_SIZE   MXC_FLASH_PAGE_SIZE

#elif defined(MAX32665) || defined(MAX32666)
#define BOARD_FLASH_ADDR_ZERO   MXC_FLASH_MEM_BASE
#define BOARD_FLASH_SIZE        (MXC_FLASH_MEM_SIZE * 2) //2 Banks of contiguous flash
#define BOARD_FLASH_PAGE_SIZE   MXC_FLASH_PAGE_SIZE

#elif defined(MAX32690)
#define BOARD_FLASH_ADDR_ZERO   MXC_FLASH0_MEM_BASE
#define BOARD_FLASH_SIZE        MXC_FLASH0_MEM_SIZE
#define BOARD_FLASH_PAGE_SIZE   MXC_FLASH0_PAGE_SIZE

#elif defined(MAX78002)
#define BOARD_FLASH_ADDR_ZERO   MXC_FLASH_MEM_BASE
#define BOARD_FLASH_SIZE        MXC_FLASH_MEM_SIZE
#define BOARD_FLASH_PAGE_SIZE   MXC_FLASH_PAGE_SIZE

#endif

#define BOARD_FLASH_ADDR_LAST   (BOARD_FLASH_ADDR_ZERO + BOARD_FLASH_SIZE - 1)
#define BOARD_FLASH_NUM_PAGES   (BOARD_FLASH_SIZE / BOARD_FLASH_PAGE_SIZE)

#ifndef FLASH_BOOT_SIZE
#error "FLASH_BOOT_SIZE must be defined"
#endif

#if ((FLASH_BOOT_SIZE % BOARD_FLASH_PAGE_SIZE) != 0)
#error "FLASH_BOOT_SIZE must be aligned on a page boundary"
#endif

#define FLASH_BOOT_NUM_PAGES        (FLASH_BOOT_SIZE / BOARD_FLASH_PAGE_SIZE)
#define BOARD_FLASH_APP_START       (BOARD_FLASH_ADDR_ZERO + FLASH_BOOT_SIZE)
#define BOARD_FLASH_APP_SIZE        (BOARD_FLASH_SIZE - FLASH_BOOT_SIZE)
#define BOARD_FLASH_APP_START_PAGE  (FLASH_BOOT_NUM_PAGES)
#define BOARD_FLASH_APP_PAGES       (BOARD_FLASH_APP_SIZE / BOARD_FLASH_PAGE_SIZE)

// Support Double tap feature
#define TINYUF2_DBL_TAP_DFU     1

// Support LED
#define TINYUF2_LED             1

#ifdef __cplusplus
 }
#endif

#endif /* BOARDS_H_ */
