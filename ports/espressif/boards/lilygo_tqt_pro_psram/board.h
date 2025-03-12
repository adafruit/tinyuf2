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

#ifndef LILYGO_TQT_PRO_PSRAM_H_
#define LILYGO_TQT_PRO_PSRAM_H_

//--------------------------------------------------------------------+
// Button
//--------------------------------------------------------------------+

// Enter UF2 mode if GPIO is pressed while 2nd stage bootloader indicator
// is on e.g RGB = Purple. If it is GPIO0, user should not hold this while
// reset since that will instead run the 1st stage ROM bootloader
#define PIN_BUTTON_UF2        0

// GPIO that implement 1-bit memory with RC components which hold the
// pin value long enough for double reset detection.
// #define PIN_DOUBLE_RESET_RC   10

//--------------------------------------------------------------------+
// TFT
//--------------------------------------------------------------------+

#define CONFIG_LCD_TYPE_GC9107

#define DISPLAY_PIN_MISO      -1 // required if use CONFIG_LCD_TYPE_AUTO
#define DISPLAY_PIN_MOSI       2
#define DISPLAY_PIN_SCK        3

#define DISPLAY_PIN_CS         5
#define DISPLAY_PIN_DC         6
#define DISPLAY_PIN_RST        1

#define DISPLAY_PIN_BL        10
#define DISPLAY_BL_ON          0  // GPIO state to enable back light

#define DISPLAY_WIDTH         128
#define DISPLAY_HEIGHT        128

#define DISPLAY_COL_OFFSET     1
#define DISPLAY_ROW_OFFSET     2

// Memory Data Access Control
#define DISPLAY_MADCTL        (TFT_MADCTL_MX | TFT_MADCTL_MY | TFT_MADCTL_MV)
// Vertical Scroll Start Address
#define DISPLAY_VSCSAD        0

#define DISPLAY_TITLE         "T-QT"

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID                  0x303a
#define USB_PID                  0x8155

#define USB_MANUFACTURER         "LILYGO"
#define USB_PRODUCT              "T-QT PRO (4M Flash, 2M PSRAM)"

#define UF2_PRODUCT_NAME         USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID             "ESP32S3-TQTPRO-N4R2"
#define UF2_VOLUME_LABEL         "TQTPROBOOT"
#define UF2_INDEX_URL            "https://lilygo.cc/products/t-qt-pro"

#endif
