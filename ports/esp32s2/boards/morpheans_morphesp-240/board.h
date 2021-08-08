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
#pragma once

//--------------------------------------------------------------------+
// Button
//--------------------------------------------------------------------+

// Enter UF2 mode if GPIO is pressed while 2nd stage bootloader indicator
// is on e.g RGB = Purple. If it is GPIO0, user should not hold this while
// reset since that will instead run the 1st stage ROM bootloader
#define PIN_BUTTON_UF2       0

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+

// GPIO connected to Neopixel data
// Note: Need to insert Jumper (default is Off) to control neopixel
// On Kaluga this pin is also connected to Camera D3
#define NEOPIXEL_PIN          16

// Brightness percentage from 1 to 255
#define NEOPIXEL_BRIGHTNESS   0x10

// Number of neopixels
#define NEOPIXEL_NUMBER       1

//--------------------------------------------------------------------+
// TFT Display ST7789
//--------------------------------------------------------------------+
// #undef  CONFIG_LCD_TYPE_AUTO
#define CONFIG_LCD_TYPE_ST7789V

#define DISPLAY_PIN_MISO    -1              //No MISO connected to display.
#define DISPLAY_PIN_MOSI    11
#define DISPLAY_PIN_SCK     12
#define DISPLAY_PIN_CS      10
#define DISPLAY_PIN_DC      14
#define DISPLAY_PIN_RST     9
#define DISPLAY_PIN_BL      21 // TODO There is no backlight control on this board. Unused pin for now. Will have to PR tinyuf2      
#define DISPLAY_BL_ON       1 // GPIO state to enable back light

#define DISPLAY_WIDTH       240
#define DISPLAY_HEIGHT      240
#define DISPLAY_MADCTL      (TFT_MADCTL_MV | TFT_MADCTL_RGB)

#define DISPLAY_VSCSAD      0
#define DISPLAY_COL_OFFSET  0
#define DISPLAY_ROW_OFFSET  0

#define DISPLAY_TITLE        "MORPHESP240"
//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID           0x303A            // Espressif VID
#define USB_PID           0x80B6            // Espressif assigned PID
#define USB_MANUFACTURER  "MORPHEANS"
#define USB_PRODUCT       "MORPHESP-240"

#define UF2_PRODUCT_NAME  USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID      "ESP32S2-MORPHESP240-v1.0"
#define UF2_VOLUME_LABEL  "MORPHBOOT"
#define UF2_INDEX_URL     "https://github.com/ccadic/ESP32-S2-DevBoardTFT"
