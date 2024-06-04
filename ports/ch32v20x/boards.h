/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2020 Ha Thach (tinyusb.org) for Adafruit Industries
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

#include "ch32v20x.h"
#include "board.h"

#define TINYUF2_DBL_TAP_DFU       1
#define TINYUF2_DBL_TAP_REG       BKP->DATAR10
#define TINYUF2_DBL_TAP_REG_SIZE  16

// symbol from linker
extern uint32_t __flash_size[];
extern uint32_t __flash_boot_size[];

#define BOARD_FLASH_SIZE        ((uint32_t) __flash_size)
#define BOARD_FLASH_APP_START   ((uint32_t) __flash_boot_size)

#ifdef __cplusplus
 }
#endif

#endif /* BOARDS_H_ */
