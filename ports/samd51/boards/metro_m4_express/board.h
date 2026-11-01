/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2026 Ha Thach for Adafruit Industries
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

// No user button: double tap reset enters the bootloader, as with uf2-samdx1
#define TINYUF2_DBL_TAP_DFU 1

//--------------------------------------------------------------------+
// Neopixel
//--------------------------------------------------------------------+

#define NEOPIXEL_NUMBER 1

#define NEOPIXEL_PORT 1
#define NEOPIXEL_PIN  22

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID          0x239A
#define USB_PID          0x0021
#define USB_MANUFACTURER "Adafruit"
#define USB_PRODUCT      "Metro M4 Express"

#define UF2_PRODUCT_NAME USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID     "SAMD51J19A-Metro-v0"
#define UF2_VOLUME_LABEL "METROM4BOOT"
#define UF2_INDEX_URL    "https://www.adafruit.com/product/3382"

#endif
