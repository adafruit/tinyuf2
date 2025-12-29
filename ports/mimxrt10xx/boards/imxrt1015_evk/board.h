/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2020 Ha Thach for Adafruit Industries
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
 *
 * This file is part of the TinyUSB stack.
 */


#ifndef BOARD_H_
#define BOARD_H_

// Size of on-board external flash
#define BOARD_FLASH_SIZE     (16*1024*1024)

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+
#define LED_PORT     BOARD_INITPINS_USER_LED_PERIPHERAL
#define LED_PIN      BOARD_INITPINS_USER_LED_CHANNEL
#define LED_STATE_ON          0

//--------------------------------------------------------------------+
// Neopixel
//--------------------------------------------------------------------+
#define NEOPIXEL_NUMBER 0 // Number of neopixels

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+
#define USB_VID           0x239A
#define USB_PID           0x0137
#define USB_MANUFACTURER  "NXP"
#define USB_PRODUCT       "RT1015 EVK"

#define UF2_PRODUCT_NAME  USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID      "MIMXRT1015-EVK-revA"
#define UF2_VOLUME_LABEL  "RT1015BOOT"
#define UF2_INDEX_URL     "https://www.nxp.com/part/MIMXRT1015-EVK#/"

//--------------------------------------------------------------------+
// UART
//--------------------------------------------------------------------+
#define UART_DEV              LPUART1

#endif /* BOARD_H_ */
