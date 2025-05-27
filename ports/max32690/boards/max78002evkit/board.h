/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2025 Brent Kowal, Analog Devices, Inc
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

#include "max78002.h"

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+

#define LED_PORT              MXC_GPIO2
#define LED_PIN               MXC_GPIO_PIN_4
#define LED_VDDIO             MXC_GPIO_VSSEL_VDDIOH
#define LED_STATE_ON          1

//--------------------------------------------------------------------+
// Neopixel
//--------------------------------------------------------------------+

// Number of neopixels
#define NEOPIXEL_NUMBER       0

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID           0x0456 //ADI
#define USB_PID           0xA010 //MAX32 TinyUF2
#define USB_MANUFACTURER  "Analog Devices"
#define USB_PRODUCT       "MAX78002EvKit"

#define UF2_PRODUCT_NAME  USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID      "MAX78002-EvKit"
#define UF2_VOLUME_LABEL  "78002BOOT"
#define UF2_INDEX_URL     "https://www.analog.com/en/resources/evaluation-hardware-and-software/evaluation-boards-kits/max78002evkit.html"

//--------------------------------------------------------------------+
// UART
//--------------------------------------------------------------------+

// UART Enable for EvKit's Integrated FTDI Adapter. Pin Mux handled by the HAL
#define UART_NUM        0
#define UART_PORT       MXC_GPIO0
#define UART_VDDIO_BITS 0xF

#endif
