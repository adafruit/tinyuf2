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

#ifndef WAVESHARE_ESP32_S3_LCD_19_H_
#define WAVESHARE_ESP32_S3_LCD_19_H_

//--------------------------------------------------------------------+
// Button
//--------------------------------------------------------------------+
// Enter UF2 mode if GPIO is pressed while 2nd stage bootloader indicator
// is on e.g RGB = Purple. If it is GPIO0, user should not hold this while
// reset since that will instead run the 1st stage ROM bootloader
#define PIN_BUTTON_UF2        0

// GPIO that implement 1-bit memory with RC components which hold the
// pin value long enough for double reset detection.
// #define PIN_DOUBLE_RESET_RC

// #define CUSTOM_PIN_BUTTON_PWR_EN

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+
// GPIO connected to Neopixel data
#define NEOPIXEL_PIN          15
// Brightness percentage from 1 to 255
#define NEOPIXEL_BRIGHTNESS   0xFF
// Number of neopixels
#define NEOPIXEL_NUMBER       2

//--------------------------------------------------------------------+
// TFT
//--------------------------------------------------------------------+
#define CONFIG_LCD_TYPE_ST7789V

#define DISPLAY_PIN_MISO      -1  // Not used for ST7789V
#define DISPLAY_PIN_MOSI      13  // LCD_DIN
#define DISPLAY_PIN_SCK       10  // LCD_CLK
#define DISPLAY_PIN_DC        11  // LCD_DC
#define DISPLAY_PIN_CS        12  // LCD_CS
#define DISPLAY_PIN_RST       9   // LCD_RST
#define DISPLAY_PIN_BL        14  // LCD_BL

#define DISPLAY_BL_ON         0   // GPIO state to enable back light

#define DISPLAY_WIDTH         320
#define DISPLAY_HEIGHT        170
#define DISPLAY_COL_OFFSET    35
#define DISPLAY_ROW_OFFSET    0

// Memory Data Access Control & Vertical Scroll Start Address
#define DISPLAY_MADCTL        (TFT_MADCTL_MX)
#define DISPLAY_VSCSAD        0
#define DISPLAY_TITLE         "ESP32S3-LCD-1.9"

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+
#define USB_VID                  0x303a  // Espressif VID
#define USB_PID                  0x8223
#define USB_MANUFACTURER         "Waveshare"
#define USB_PRODUCT              "ESP32-S3_LCD_1.9"
#define UF2_PRODUCT_NAME         USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID             "ESP32S3-LCD_1.9-v0"
#define UF2_VOLUME_LABEL         "S3-LCD-BOOT"
#define UF2_INDEX_URL            "https://www.waveshare.com/esp32-s3-lcd-1.9.htm"

#endif
