/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2024 Robert Grizzell, Independently providing these changes
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

#ifndef LILYGO_TDISPLAY_S3_H_
#define LILYGO_TDISPLAY_S3_H_

//--------------------------------------------------------------------+
// Button
//--------------------------------------------------------------------+

// Enter UF2 mode if GPIO is pressed while 2nd stage bootloader indicator
// is on e.g RGB = Purple. If it is GPIO0, user should not hold this while
// reset since that will instead run the 1st stage ROM bootloader
#define PIN_BUTTON_UF2       0

// GPIO that implement 1-bit memory with RC components which hold the
// pin value long enough for double reset detection.
// #define PIN_DOUBLE_RESET_RC   38

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+

// No LED onboard.

//--------------------------------------------------------------------+
// TFT
//--------------------------------------------------------------------+
//
//Parallel Bus Display - Enable when support is added
//#define CONFIG_LCD_TYPE_ST7789V
//
//#define DISPLAY_PIN_MISO      -1 // required if use CONFIG_LCD_TYPE_AUTO
//#define DISPLAY_PIN_MOSI      -1
//#define DISPLAY_PIN_SCK       -1
//
//#define DISPLAY_PIN_D0        39 // Data 0
//#define DISPLAY_PIN_D1        40 // Data 1
//#define DISPLAY_PIN_D2        41 // Data 2
//#define DISPLAY_PIN_D3        42 // Data 3
//#define DISPLAY_PIN_D4        45 // Data 4
//#define DISPLAY_PIN_D5        46 // Data 5
//#define DISPLAY_PIN_D6        47 // Data 6
//#define DISPLAY_PIN_D7        48 // Data 7
//#define DISPLAY_PIN_WR        08 // Write
//#define DISPLAY_PIN_RD        09 // Read
//#define DISPLAY_PIN_CS        06 // Chip Select
//#define DISPLAY_PIN_DC        07 // Command
//#define DISPLAY_PIN_RST       05 // Rest
//
//#define DISPLAY_PIN_BL        38
//#define DISPLAY_BL_ON          1  // GPIO state to enable back light
//
//#define DISPLAY_PIN_POWER     15
//#define DISPLAY_POWER_ON       1  // GPIO state to enable TFT
//
//#define DISPLAY_WIDTH         320
//#define DISPLAY_HEIGHT        170
//
//#define DISPLAY_COL_OFFSET    0
//#define DISPLAY_ROW_OFFSET    35
//
// Memory Data Access Control & // Vertical Scroll Start Address
//#define DISPLAY_MADCTL        (TFT_MADCTL_MX)
//#define DISPLAY_VSCSAD        0
//
//#define DISPLAY_TITLE         "T-Display S3"

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID                  0x303A
#define USB_PID                  0x8140

#define USB_MANUFACTURER         "LILYGO"
#define USB_PRODUCT              "T-Display S3"

#define UF2_PRODUCT_NAME         USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID             "ESP32S3-T-Display-S3"
#define UF2_VOLUME_LABEL         "TDISPBOOT"
#define UF2_INDEX_URL            "https://github.com/Xinyuan-LilyGO/T-Display-S3"

#endif
