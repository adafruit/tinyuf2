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

#ifndef ESPRESSIF_SAOLA_1_WROVER_H_
#define ESPRESSIF_SAOLA_1_WROVER_H_

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+

// GPIO connected to Neopixel data
// Note: Need to insert Jumper (default is Off) to control neopixel
// On Kaluga this pin is also connected to Camera D3
#define PIN_NEOPIXEL          45

// Brightness percentage from 1 to 255
#define NEOPIXEL_BRIGHTNESS   0x10

// Number of neopixels
#define NEOPIXEL_NUMBER       1

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define UF2_PRODUCT_NAME "Espressif Kaluga 1"
#define UF2_BOARD_ID     "ESP32S2-Kaluga-v1.2"
#define UF2_VOLUME_LABEL "KALUGA1BOOT"
#define UF2_INDEX_URL    "https://docs.espressif.com/projects/esp-idf/en/latest/esp32s2/hw-reference/esp32s2/user-guide-esp32-s2-kaluga-1-kit.html"


#endif
