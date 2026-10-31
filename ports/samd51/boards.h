/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2026 Intech Studio
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
 *
 */

#ifndef BOARDS_H_
#define BOARDS_H_

#ifdef __cplusplus
extern "C" {
#endif

#include "sam.h"

#include "board.h"

#define BOARD_FLASH_ADDR_ZERO 0x00000000
// from the device header of the part the board selects
#define BOARD_FLASH_SIZE      FLASH_SIZE

// Flash Start Address of Application
#ifndef BOARD_FLASH_APP_START
extern uint32_t __flash_boot_size[];
  #define BOARD_FLASH_APP_START (BOARD_FLASH_ADDR_ZERO + (uint32_t)__flash_boot_size)
#endif

// Initial stack pointer inside SRAM, and reset handler a Thumb address in [start, end)
static inline bool vector_table_valid(uint32_t sp, uint32_t entry, uint32_t start, uint32_t end) {
  return (sp & 3u) == 0 && sp > HSRAM_ADDR && sp <= HSRAM_ADDR + HSRAM_SIZE && (entry & 1u) != 0 && entry >= start &&
         entry < end;
}

// Enable write protection
#ifndef TINYUF2_PROTECT_BOOTLOADER
  #define TINYUF2_PROTECT_BOOTLOADER 1
#endif

// Brightness scale, in 256ths
#ifndef NEOPIXEL_BRIGHTNESS
  #define NEOPIXEL_BRIGHTNESS 0x10
#endif

#ifdef __cplusplus
}
#endif

#endif /* BOARDS_H_ */
