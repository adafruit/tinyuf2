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

#ifndef ADAFRUIT_FUNHOUSE_ESP32S2_H_
#define ADAFRUIT_FUNHOUSE_ESP32S2_H_

//--------------------------------------------------------------------+
// Button
//--------------------------------------------------------------------+

// Enter UF2 mode if GPIO is pressed while 2nd stage bootloader indicator
// is on e.g RGB = Purple. If it is GPIO0, user should not hold this while
// reset since that will instead run the 1st stage ROM bootloader
#define PIN_BUTTON_UF2        0

// GPIO that implement 1-bit memory with RC components which hold the
// pin value long enough for double reset detection.
#define PIN_DOUBLE_RESET_RC   38

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+

// Number of Dotstar
#define DOTSTAR_NUMBER        5

// GPIO connected to Dotstar
#define DOTSTAR_PIN_DATA      14
#define DOTSTAR_PIN_SCK       15
//#define DOTSTAR_PIN_PWR       41
//#define DOTSTAR_POWER_STATE   0

// Brightness percentage from 1 to 255
#define DOTSTAR_BRIGHTNESS    0x08

// LED for indicator
// If not defined neopixel will be use for flash writing instead
#define LED_PIN               37
#define LED_STATE_ON          1

//--------------------------------------------------------------------+
// TFT
//--------------------------------------------------------------------+

#define CONFIG_LCD_TYPE_ST7789V

#define DISPLAY_PIN_MISO      -1 // required if use CONFIG_LCD_TYPE_AUTO
#define DISPLAY_PIN_MOSI      35
#define DISPLAY_PIN_SCK       36

#define DISPLAY_PIN_CS        40
#define DISPLAY_PIN_DC        39
#define DISPLAY_PIN_RST       41

#define DISPLAY_PIN_BL        21
#define DISPLAY_BL_ON         1  // GPIO state to enable back light

#define DISPLAY_WIDTH         240
#define DISPLAY_HEIGHT        320

#define DISPLAY_COL_OFFSET    0
#define DISPLAY_ROW_OFFSET    0

// Memory Data Access Control & // Vertical Scroll Start Address
#define DISPLAY_MADCTL        (TFT_MADCTL_MX | TFT_MADCTL_MY | TFT_MADCTL_MV)
#define DISPLAY_VSCSAD        140

#define DISPLAY_TITLE         "Fun House"

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID                  0x239A
#define USB_PID                  0x00F9
#define USB_MANUFACTURER         "Adafruit"
#define USB_PRODUCT              "FunHouse"

#define UF2_PRODUCT_NAME         USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID             "ESP32S2-FunHouse-revB"
#define UF2_VOLUME_LABEL         "HOUSEBOOT"
#define UF2_INDEX_URL            "https://www.adafruit.com/"

// Use favicon
#define TINYUF2_FAVICON_HEADER   "favicon_adafruit_256.h"

#endif
