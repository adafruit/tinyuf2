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

#ifndef LILYGO_TDONGLE_S3_H_
#define LILYGO_TDONGLE_S3_H_

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

// Number of Dotstar
#define DOTSTAR_NUMBER        1

// GPIO connected to Dotstar
#define DOTSTAR_PIN_DATA      40
#define DOTSTAR_PIN_SCK       39

// Brightness percentage from 1 to 255
#define DOTSTAR_BRIGHTNESS     127

//--------------------------------------------------------------------+
// TFT
//--------------------------------------------------------------------+
//

// LCD is ST7735 and may need a custom init cmd to use the ILI9341 driver.
// #define CONFIG_LCD_TYPE_ILI9341

// #define DISPLAY_PIN_MISO       -1 // required if use CONFIG_LCD_TYPE_AUTO
// #define DISPLAY_PIN_MOSI        3
// #define DISPLAY_PIN_SCK         5

// #define DISPLAY_PIN_CS          4
// #define DISPLAY_PIN_DC          2
// #define DISPLAY_PIN_RST         1

// #define DISPLAY_PIN_BL         38
// #define DISPLAY_BL_ON           1 // GPIO state to enable back light

// #define DISPLAY_PIN_POWER      -1
// #define DISPLAY_POWER_ON        1 // GPIO state to enable TFT

// #define DISPLAY_WIDTH         160
// #define DISPLAY_HEIGHT         80

// #define DISPLAY_COL_OFFSET     26
// #define DISPLAY_ROW_OFFSET      1

// Memory Data Access Control & // Vertical Scroll Start Address
// #define DISPLAY_MADCTL        (TFT_MADCTL_BGR | TFT_MADCTL_MY | TFT_MADCTL_MV)
// #define DISPLAY_VSCSAD        80
// Display rotated 90 degrees

// #define DISPLAY_TITLE         "T-Dongle-S3"

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID                  0x303A
#define USB_PID                  0x82C3

#define USB_MANUFACTURER         "LILYGO"
#define USB_PRODUCT              "T-Dongle S3"

#define UF2_PRODUCT_NAME         USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID             "ESP32S3-T_Dongle_S3-rev2" // Rev. 2 added a QWIIC connector
#define UF2_VOLUME_LABEL         "LILYGOBOOT"
#define UF2_INDEX_URL            "https://github.com/Xinyuan-LilyGO/T-Dongle-S3"

#endif
