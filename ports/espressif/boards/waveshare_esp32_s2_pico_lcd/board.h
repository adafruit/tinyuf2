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

#ifndef WAVESHARE_ESP32_S2_PICO_LCD_
#define WAVESHARE_ESP32_S2_PICO_LCD_

//--------------------------------------------------------------------+
// Button
//--------------------------------------------------------------------+

#define PIN_BUTTON_UF2        0

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+


// #define LED_PIN               9
// #define LED_STATE_ON          0

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID           0x303a
#define USB_PID           0x810b
#define USB_MANUFACTURER  "Waveshare Electronics"
#define USB_PRODUCT       "ESP32-S2-Pico-LCD"

#define UF2_PRODUCT_NAME  USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID      "ESP32-S2-Pico-LCD"
#define UF2_VOLUME_LABEL  "ESP32S2PICO"
#define UF2_INDEX_URL     "http://www.waveshare.com/wiki/ESP32-S2-Pico"

#endif
