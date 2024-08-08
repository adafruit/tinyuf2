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

#ifndef WAVESHARE_ESP32_S3_TOUCH_LCD_169_H_
#define WAVESHARE_ESP32_S3_TOUCH_LCD_169_H_

//--------------------------------------------------------------------+
// Button
//--------------------------------------------------------------------+

// Enter UF2 mode if GPIO is pressed while 2nd stage bootloader indicator
// is on e.g RGB = Purple. If it is GPIO0, user should not hold this while
// reset since that will instead run the 1st stage ROM bootloader
#define PIN_BUTTON_UF2        0

// GPIO that implement 1-bit memory with RC components which hold the
// pin value long enough for double reset detection.
#define PIN_DOUBLE_RESET_RC   36

#define CUSTOM_PIN_BUTTON_PWR_EN   35

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+

// No LED onboard.

//--------------------------------------------------------------------+
// TFT
//--------------------------------------------------------------------+
#define CONFIG_LCD_TYPE_ST7789V

#define DISPLAY_PIN_MISO      -1 // required if use CONFIG_LCD_TYPE_AUTO
#define DISPLAY_PIN_MOSI       7
#define DISPLAY_PIN_SCK        6

#define DISPLAY_PIN_CS         5
#define DISPLAY_PIN_DC         4
#define DISPLAY_PIN_RST        8

#define DISPLAY_PIN_BL        15
#define DISPLAY_BL_ON          1  // GPIO state to enable back light

#define DISPLAY_PIN_POWER     -1
#define DISPLAY_POWER_ON       1  // GPIO state to enable TFT

#define DISPLAY_WIDTH         240
#define DISPLAY_HEIGHT        280

#define DISPLAY_COL_OFFSET    20
#define DISPLAY_ROW_OFFSET    0

// Memory Data Access Control & Vertical Scroll Start Address
#define DISPLAY_MADCTL        (TFT_MADCTL_MX)
#define DISPLAY_VSCSAD        0

#define DISPLAY_TITLE         "WS-DISPLAY"

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID                  0x303a
#define USB_PID                  0x8220
#define USB_MANUFACTURER         "Waveshare Electronics"
#define USB_PRODUCT              "ESP32-S3-Touch-LCD-1.69"

#define UF2_PRODUCT_NAME         USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID             "ESP32-S3-Touch-LCD-1.69"
#define UF2_VOLUME_LABEL         "WSS3BOOT"
#define UF2_INDEX_URL            "https://www.waveshare.com/product/esp32-s3-touch-lcd-1.69.htm"

#endif
