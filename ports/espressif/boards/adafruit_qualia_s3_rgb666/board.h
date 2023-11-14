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

#ifndef ADAFRUIT_QUALIA_S3_H_
#define ADAFRUIT_QUALIA_S3_H_

//--------------------------------------------------------------------+
// Button
//--------------------------------------------------------------------+

// Enter UF2 mode if GPIO is pressed while 2nd stage bootloader indicator
// is on e.g RGB = Purple. If it is GPIO0, user should not hold this while
// reset since that will instead run the 1st stage ROM bootloader
#define PIN_BUTTON_UF2        0

// GPIO that implement 1-bit memory with RC components which hold the
// pin value long enough for double reset detection.
#define PIN_DOUBLE_RESET_RC   4

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID                  0x239A
#define USB_PID                  0x0147
#define USB_MANUFACTURER         "Adafruit"
#define USB_PRODUCT              "Qualia ESP32-S3 RGB666"

#define UF2_PRODUCT_NAME         USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID             "ESP32S3-Qualia-revC"
#define UF2_VOLUME_LABEL         "TFT_S3BOOT"
#define UF2_INDEX_URL            "https://www.adafruit.com/5800"

// Use favicon
#define TINYUF2_FAVICON_HEADER   "favicon_adafruit_256.h"

#endif
