/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2018 Ha Thach for Adafruit Industries
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

#ifndef BOARD_H_
#define BOARD_H_

//--------------------------------------------------------------------+
// Button
//--------------------------------------------------------------------+

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+

#define LED_PORT              GPIOC
#define LED_PIN               GPIO_PIN_1
#define LED_STATE_ON          1

//--------------------------------------------------------------------+
// Neopixel
//--------------------------------------------------------------------+

#define NEOPIXEL_PORT         GPIOC
#define NEOPIXEL_PIN          GPIO_PIN_0

// Brightness percentage from 1 to 255
#define NEOPIXEL_BRIGHTNESS   0x10

// Number of neopixels
#define NEOPIXEL_NUMBER       1

//--------------------------------------------------------------------+
// Flash
//--------------------------------------------------------------------+

// Flash size of the board
#define BOARD_FLASH_SIZE  (1024 * 1024)

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID           0x239A
#define USB_PID           0x0059
#define USB_MANUFACTURER  "Adafruit"
#define USB_PRODUCT       "Feather STM32F405 Express"

#define UF2_PRODUCT_NAME  USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID      "STM32F405-Feather-revB"
#define UF2_VOLUME_LABEL  "FTHR405BOOT"
#define UF2_INDEX_URL     "https://www.adafruit.com/product/4382"


#endif
