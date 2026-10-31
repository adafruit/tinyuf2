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

#ifndef BOARD_H_
#define BOARD_H_

//--------------------------------------------------------------------+
// Button, pulled up and active low. Holding it at reset enters the bootloader
//--------------------------------------------------------------------+
#define BUTTON_PORT         2
#define BUTTON_PIN          11
#define BUTTON_STATE_ACTIVE 0

//--------------------------------------------------------------------+
// Neopixel
//--------------------------------------------------------------------+

// Number of neopixels
#define NEOPIXEL_NUMBER 16
// Brightness scale, in 256ths
#define NEOPIXEL_BRIGHTNESS 0x08

#define NEOPIXEL_PORT       1
#define NEOPIXEL_PIN        30

// Neopixel supply enable, STATE is the level that switches it on
#define NEOPIXEL_POWER_PORT  2
#define NEOPIXEL_POWER_PIN   14
#define NEOPIXEL_POWER_STATE 1

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID          0x03EB
#define USB_PID          0x2402
#define USB_MANUFACTURER "Intech Studio"
#define USB_PRODUCT      "Bootloader 2026-10"

#define UF2_PRODUCT_NAME USB_PRODUCT
#define UF2_BOARD_ID     "SAMD51N20A-GRID-v0"
#define UF2_VOLUME_LABEL "GRID26"
#define UF2_INDEX_URL    "https://github.com/intechstudio/grid-fw/"

#endif
