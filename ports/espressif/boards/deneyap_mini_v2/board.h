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

#ifndef DENEYAP_MINI_V2_H_
#define DENEYAP_MINI_V2_H_

//--------------------------------------------------------------------+
// Button
//--------------------------------------------------------------------+

// Enter UF2 mode if GPIO is pressed while 2nd stage bootloader indicator
// is on e.g RGB = Purple. If it is GPIO0, user should not hold this while
// reset since that will instead run the 1st stage ROM bootloader
#define PIN_BUTTON_UF2        0


//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+


// LED for indicator and writing flash
// If not defined neopixel will be use for flash writing instead
#define LED_PIN               33
#define LED_STATE_ON          1

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID                  0x303A
#define USB_PID                  0x8146
#define USB_MANUFACTURER         "T3 Foundation"
#define USB_PRODUCT              "Deneyap Mini v2"

#define UF2_PRODUCT_NAME         USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID             "ESP32S2-DeneyapMini-v2"
#define UF2_VOLUME_LABEL         "DYM2BOOT"
#define UF2_INDEX_URL            "https://magaza.deneyapkart.org/tr/product/detail/deneyap-mini-v2-type-c"

#endif
