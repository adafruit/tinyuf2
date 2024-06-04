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

#include "sdkconfig.h"
#include "board.h"

// Family ID for updating Application
#if CONFIG_IDF_TARGET_ESP32S2
  #define BOARD_UF2_FAMILY_ID     0xbfdd4eee
#elif CONFIG_IDF_TARGET_ESP32S3
  #define BOARD_UF2_FAMILY_ID     0xc47e5767
#else
  #error unsupported MCUs
#endif


// Flash Start Address of Application
#define BOARD_FLASH_APP_START   0

// Double Reset tap to enter DFU, for ESP this is done in bootloader subproject
#define TINYUF2_DBL_TAP_DFU     0

#ifdef DISPLAY_PIN_SCK
 #define TINYUF2_DISPLAY 1
#endif

#ifdef __cplusplus
 }
#endif

#endif /* BOARDS_H_ */
