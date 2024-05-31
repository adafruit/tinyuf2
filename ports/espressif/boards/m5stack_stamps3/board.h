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


#ifndef M5STACK_STAMPS3_BOARD_H_
#define M5STACK_STAMPS3_BOARD_H_

//--------------------------------------------------------------------+
// Button
//--------------------------------------------------------------------+

// Enter UF2 mode if GPIO is pressed while 2nd stage bootloader indicator
// is on e.g RGB = Purple. If it is GPIO0, user should not hold this while
// reset since that will instead run the 1st stage ROM bootloader
#define PIN_BUTTON_UF2        0

// GPIO that implement 1-bit memory with RC components which hold the
// pin value long enough for double reset detection.
//#define PIN_DOUBLE_RESET_RC

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+

// GPIO connected to Neopixel data
#define NEOPIXEL_PIN          21

// Brightness percentage from 1 to 255
#define NEOPIXEL_BRIGHTNESS   0x10

// Number of neopixels
#define NEOPIXEL_NUMBER       1

//--------------------------------------------------------------------+
// TFT
//--------------------------------------------------------------------+

#define CONFIG_LCD_TYPE_ST7789V

#define DISPLAY_PIN_MISO      -1 // required if use CONFIG_LCD_TYPE_AUTO
#define DISPLAY_PIN_MOSI      35
#define DISPLAY_PIN_SCK       36

#define DISPLAY_PIN_CS        37
#define DISPLAY_PIN_DC        34
#define DISPLAY_PIN_RST       33

#define DISPLAY_PIN_BL        45
#define DISPLAY_BL_ON          1  // GPIO state to enable back light

#define DISPLAY_PIN_POWER     38
#define DISPLAY_POWER_ON       1  // GPIO state to enable TFT

#define DISPLAY_WIDTH         240
#define DISPLAY_HEIGHT        135

#define DISPLAY_COL_OFFSET    53
#define DISPLAY_ROW_OFFSET    40

// Memory Data Access Control & // Vertical Scroll Start Address
#define DISPLAY_MADCTL        (TFT_MADCTL_MX)
#define DISPLAY_VSCSAD        0

#define DISPLAY_TITLE         "M5Stamp S3"

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID                  0x303A
#define USB_PID                  0x811A

#define USB_MANUFACTURER         "M5Stack"
#define USB_PRODUCT              "Stamp S3"

#define UF2_PRODUCT_NAME         USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID             "ESP32S3-StampS3-01"
#define UF2_VOLUME_LABEL         "M5S3BOOT"
#define UF2_INDEX_URL            "https://docs.m5stack.com/en/core/StampS3"

#endif
