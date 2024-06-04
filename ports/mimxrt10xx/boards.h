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

#define SEQUENCE(first, second, third, fourth) first, second, third, fourth
#define TWO_EMPTY_STEPS 0x00000000
#define EMPTY_SEQUENCE SEQUENCE(TWO_EMPTY_STEPS, TWO_EMPTY_STEPS, TWO_EMPTY_STEPS, TWO_EMPTY_STEPS)

#include "fsl_device_registers.h"
#include "board.h"

// symbols defined in linker script
extern uint32_t _ivt_origin[];
extern uint32_t _board_boot_length[];

// The FCFB has different offsets, but the IVT is consistent within the family
#define BOARD_BOOT_START        (((uint32_t) _ivt_origin) - 0x1000)

// The ROM bootloader loader needs instructed to
// copy the text section, IVT structure and interrupt table.
#define BOARD_BOOT_LENGTH       ((uint32_t) &_board_boot_length)

// Flash Start Address of Application, typically 0x6000C000
#ifndef BOARD_FLASH_APP_START
#ifdef FlexSPI1_AMBA_BASE
#define BOARD_FLASH_APP_START   (FlexSPI1_AMBA_BASE + 0xC000)
#else
#define BOARD_FLASH_APP_START   (FlexSPI_AMBA_BASE + 0xC000)
#endif
#endif

// Double Reset tap to enter DFU
#define TINYUF2_DBL_TAP_DFU     1
#define TINYUF2_DBL_TAP_REG     SNVS->LPGPR[3]

// Brightness percentage from 1 to 255
#ifndef NEOPIXEL_BRIGHTNESS
#define NEOPIXEL_BRIGHTNESS     0x10
#endif

#ifdef LED_PIN
#define TINYUF2_LED             1
#endif

#ifdef __cplusplus
 }
#endif

#endif /* BOARDS_H_ */
