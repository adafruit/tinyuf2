/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2020 Ha Thach (tinyusb.org) for Adafruit Industries
 * Copyright (c) 2023 Linar Yusupov
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
#define PIN_BUTTON_UF2    0

// Initial delay in milliseconds to detect user interaction to enter UF2
#define UF2_DETECTION_DELAY_MS  1000

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+

// LED for indicator and writing flash
//#define LED_PIN           18
//#define LED_STATE_ON      1

//--------------------------------------------------------------------+
// TFT
//--------------------------------------------------------------------+

#define CONFIG_LCD_TYPE_ST7789V

#define DISPLAY_PIN_MISO      -1 // required if use CONFIG_LCD_TYPE_AUTO
#define DISPLAY_PIN_MOSI      48
#define DISPLAY_PIN_SCK       38

#define DISPLAY_PIN_CS        39
#define DISPLAY_PIN_DC        47
#define DISPLAY_PIN_RST       40

#define DISPLAY_PIN_BL        7
#define DISPLAY_BL_ON         0  // GPIO state to enable back light

#define DISPLAY_PIN_POWER     17
#define DISPLAY_POWER_ON       1  // GPIO state to enable TFT

#define DISPLAY_WIDTH         320
#define DISPLAY_HEIGHT        170

#define DISPLAY_COL_OFFSET    35
#define DISPLAY_ROW_OFFSET    0

// Memory Data Access Control & // Vertical Scroll Start Address
// Rotate display by changing MY to MX below
#define DISPLAY_MADCTL        TFT_MADCTL_MY
#define DISPLAY_VSCSAD        0

#define DISPLAY_TITLE         "Heltec T190"

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID           0x303A            // Espressif VID
#define USB_PID           0x1001            // Espressif assigned PID
#define USB_MANUFACTURER  "Heltec"
#define USB_PRODUCT       "Vision Master T190"

#define UF2_PRODUCT_NAME  USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID      "ESP32S3-HT-VMT190-v1.0"
#define UF2_VOLUME_LABEL  "HTBOOT"
#define UF2_INDEX_URL     "https://heltec.org/project/vision-master-t190"
