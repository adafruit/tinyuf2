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

#ifndef MATRIX_BLOCK6_PT2_H_
#define MATRIX_BLOCK6_PT2_H_

#define MATRIX
#define FASTBOOT
#define CUSTOM_LED

//--------------------------------------------------------------------+
// Button
//--------------------------------------------------------------------+

// Enter UF2 mode if GPIO is pressed while 2nd stage bootloader indicator
// is on e.g RGB = Purple. If it is GPIO0, user should not hold this while
// reset since that will instead run the 1st stage ROM bootloader
#define PIN_BUTTON_UF2        16

// GPIO that implement 1-bit memory with RC components which hold the
// pin value long enough for double reset detection.
// #define PIN_DOUBLE_RESET_RC

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+

// GPIO connected to Neopixel data
// Note: On the production version Saola (v1.2) it is GPIO 18,
// however on earlier revision v1.1 it is GPIO 17
#define NEOPIXEL_PIN          38

// Brightness percentage from 1 to 255
#define NEOPIXEL_BRIGHTNESS   0x20

// Number of neopixels
#define NEOPIXEL_NUMBER       64
// LED for indicator
// If not defined neopixel will be use for flash writing instead
// #define LED_PIN               33
// #define LED_STATE_ON          0

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID           0x0203
#define USB_PID           0x00A1
#define USB_MANUFACTURER  "203 Electronics"
#define USB_PRODUCT       "Matrix DFU"

#define UF2_PRODUCT_NAME  "203 | Matrix Pro"
#define UF2_BOARD_ID      "MATRIX-PRO}"
#define UF2_VOLUME_LABEL  "MATRIXDFU"
#define UF2_INDEX_URL     "https://203.io"

// Use favicon
#define TINYUF2_FAVICON_HEADER   "favicon_matrix_256.h"

#endif
