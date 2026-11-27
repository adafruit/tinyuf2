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
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */

#ifndef SEEED_XIAO_ESP32S31_H_
#define SEEED_XIAO_ESP32S31_H_

//--------------------------------------------------------------------+
// Button
//--------------------------------------------------------------------+

// Enter UF2 mode if GPIO is pressed while 2nd stage bootloader indicator
// is on e.g LED = on. GPIO61 is the download strapping pin: holding it
// while reset runs the 1st stage ROM bootloader instead
#define PIN_BUTTON_UF2        61

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+

// User LED (D3, yellow) wired from 3V3 through a series resistor to GPIO23,
// lights while GPIO23 is driven LOW
#define LED_PIN               23
#define LED_STATE_ON          0

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID           0x2886
#define USB_PID           0x0096

#define USB_MANUFACTURER  "Seeed Studio"
#define USB_PRODUCT       "XIAO ESP32-S31 Sense"

#define UF2_PRODUCT_NAME  USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID      "ESP32S31-XIAO-v1.0"
#define UF2_VOLUME_LABEL  "XIAOS31BOOT"
// TODO update to the wiki/product page once the board is released
#define UF2_INDEX_URL     "https://wiki.seeedstudio.com/"

#endif
