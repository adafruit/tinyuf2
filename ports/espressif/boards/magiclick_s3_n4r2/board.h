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

#ifndef MAGICLICK_S3_N4R2_H_
#define MAGICLICK_S3_N4R2_H_

//--------------------------------------------------------------------+
// Button
//--------------------------------------------------------------------+

// Enter UF2 mode if GPIO is pressed while 2nd stage bootloader indicator
// is on e.g RGB = Purple. If it is GPIO0, user should not hold this while
// reset since that will instead run the 1st stage ROM bootloader
#define PIN_BUTTON_UF2        0

// GPIO that implement 1-bit memory with RC components which hold the
// pin value long enough for double reset detection.
#define PIN_DOUBLE_RESET_RC   6

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+

// GPIO connected to Neopixel data
#define NEOPIXEL_PIN          17

// #define NEOPIXEL_POWER_PIN    -1
#define NEOPIXEL_POWER_STATE  1

// Brightness percentage from 1 to 255
#define NEOPIXEL_BRIGHTNESS   0x10

// Number of neopixels
#define NEOPIXEL_NUMBER       2

// LED for indicator and writing flash
// If not defined neopixel will be use for flash writing instead
// #define LED_PIN               -1
#define LED_STATE_ON          1

//--------------------------------------------------------------------+
// TFT
//--------------------------------------------------------------------+

#define CONFIG_LCD_TYPE_GC9107

#define DISPLAY_PIN_MISO      -1 // required if use CONFIG_LCD_TYPE_AUTO
#define DISPLAY_PIN_MOSI      4
#define DISPLAY_PIN_SCK       5

#define DISPLAY_PIN_CS         9
#define DISPLAY_PIN_DC        38
#define DISPLAY_PIN_RST       10

#define DISPLAY_PIN_BL        37
#define DISPLAY_BL_ON          1  // GPIO state to enable back light

// #define DISPLAY_PIN_POWER     -1
#define DISPLAY_POWER_ON       1  // GPIO state to enable TFT

#define DISPLAY_WIDTH         128
#define DISPLAY_HEIGHT        128

#define DISPLAY_COL_OFFSET    1
#define DISPLAY_ROW_OFFSET    2

// Memory Data Access Control & // Vertical Scroll Start Address
#define DISPLAY_MADCTL        (TFT_MADCTL_MX | TFT_MADCTL_MY | TFT_MADCTL_MV  |TFT_MADCTL_BGR)
#define DISPLAY_VSCSAD        0

#define DISPLAY_TITLE         "MagiClick S3 "

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID                  0x303A
#define USB_PID                  0x81AC

#define USB_MANUFACTURER         "MakerM0"
#define USB_PRODUCT              "MagiClick S3"

#define UF2_PRODUCT_NAME         USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID             "ESP32S3-MagiClick-revA"
#define UF2_VOLUME_LABEL         "MAGICS3BOOT"
#define UF2_INDEX_URL            "https://github.com/MakerM0/MagiClick-esp32s3"


#endif
