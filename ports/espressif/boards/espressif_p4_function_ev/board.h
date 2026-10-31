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

#ifndef ESPRESSIF_P4_FUNCTION_EV_H_
#define ESPRESSIF_P4_FUNCTION_EV_H_

//--------------------------------------------------------------------+
// Button
//--------------------------------------------------------------------+

// Enter UF2 mode if GPIO is pressed while 2nd stage bootloader is running.
// BOOT button is GPIO35, user should not hold this while reset since that
// will instead run the 1st stage ROM bootloader
#define PIN_BUTTON_UF2        35

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+

// No user LED on this board

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

// TinyUF2 runs on OTG HS (USB 2.0 Type-C port J15)
#define USB_VID           0x303A
#define USB_PID           0x7012
#define USB_MANUFACTURER  "Espressif"
#define USB_PRODUCT       "ESP32P4 Function EV"

#define UF2_PRODUCT_NAME  USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID      "ESP32P4-FunctionEV-v1.4"
#define UF2_VOLUME_LABEL  "P4FEVBOOT"
#define UF2_INDEX_URL     "https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32p4/esp32-p4-function-ev-board/index.html"

#endif
