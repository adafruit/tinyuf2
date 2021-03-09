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

#ifndef ESPRESSIF_KALUGA_1_H_
#define ESPRESSIF_KALUGA_1_H_

//--------------------------------------------------------------------+
// Button
//--------------------------------------------------------------------+

// Enter UF2 mode if GPIO is pressed while 2nd stage bootloader indicator
// is on e.g RGB = Purple. If it is GPIO0, user should not hold this while
// reset since that will instead run the 1st stage ROM bootloader
#define PIN_BUTTON_UF2        0

// GPIO that implement 1-bit memory with RC components which hold the
// pin value long enough for double reset detection.
// #define PIN_DOUBLE_RESET_RC   16

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+

// GPIO connected to Neopixel data
// Note: Need to insert Jumper (default is Off) to control neopixel
// On Kaluga this pin is also connected to Camera D3
#define NEOPIXEL_PIN          45

// Brightness percentage from 1 to 255
#define NEOPIXEL_BRIGHTNESS   0x10

// Number of neopixels
#define NEOPIXEL_NUMBER       1

//--------------------------------------------------------------------+
// TFT Display
//--------------------------------------------------------------------+

#define CONFIG_LCD_TYPE_ILI9341

#define DISPLAY_PIN_MISO      -1 // required if use CONFIG_LCD_TYPE_AUTO
#define DISPLAY_PIN_MOSI      9
#define DISPLAY_PIN_SCK       15
#define DISPLAY_PIN_CS        11

#define DISPLAY_PIN_DC        13
#define DISPLAY_PIN_RST       16
#define DISPLAY_PIN_BL        6
#define DISPLAY_BL_ON         0  // GPIO state to enable back light

#define DISPLAY_WIDTH         320
#define DISPLAY_HEIGHT        240

#define DISPLAY_COL_OFFSET    0
#define DISPLAY_ROW_OFFSET    0

// Memory Data Access Control & // Vertical Scroll Start Address
#define DISPLAY_MADCTL        TFT_MADCTL_BGR
#define DISPLAY_VSCSAD        0

#define DISPLAY_TITLE         USB_PRODUCT

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID           0x239A
#define USB_PID           0x00C7
#define USB_MANUFACTURER  "Espressif"
#define USB_PRODUCT       "Kaluga 1"

#define UF2_PRODUCT_NAME  USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID      "ESP32S2-Kaluga-v1.2"
#define UF2_VOLUME_LABEL  "KALUGA1BOOT"
#define UF2_INDEX_URL     "https://docs.espressif.com/projects/esp-idf/en/latest/esp32s2/hw-reference/esp32s2/user-guide-esp32-s2-kaluga-1-kit.html"


#endif
