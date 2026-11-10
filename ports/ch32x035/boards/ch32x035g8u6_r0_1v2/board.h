/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2026 Ha Thach for Adafruit Industries
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
// LED
//--------------------------------------------------------------------+
// CH32X035G8U6-R0-1V2 EVT board has no fixed LED wiring: LED1/LED2 nets (D4/D3,
// active low, see EVT/PUB schematic) land on the 2-pin "LED" header. Jumper a
// header GPIO to LED1; this port uses PB12 by convention.
#define LED_PORT         GPIOB
#define LED_PIN          GPIO_Pin_12
#define LED_STATE_ON     0 // low side of 3V3 -> R3/R6 -> LED
#define LED_CLOCK_EN()   RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOB, ENABLE)

//--------------------------------------------------------------------+
// Button
//--------------------------------------------------------------------+
// The EVT "Download" key is wired to PC17 which is USB D+: it only selects the
// ROM ISP boot mode and cannot be used as a user button. Enter the bootloader
// with a double tap of the RESET key instead (TINYUF2_DBL_TAP_DFU).

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

// WCH's own VID (0x1A86) with the USBFS MSC demo PID, per the SDK EVT examples
// (EVT/EXAM/USB/USBFS/DEVICE/MSC_U-Disk). Seeed boards get their own allocation.
#define USB_VID           0x1A86
#define USB_PID           0xFE10
#define USB_MANUFACTURER  "WCH"
#define USB_PRODUCT       "CH32X035G8U6 EVT"

#define UF2_PRODUCT_NAME  USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID      "WCH-CH32X035G8U6-EVT-R0-1V2"
#define UF2_VOLUME_LABEL  "X035BOOT"
#define UF2_INDEX_URL     "https://www.wch.cn"

//--------------------------------------------------------------------+
// UART
//--------------------------------------------------------------------+
// USART2 TX on PA2 (header P1 pin 7, also the ROM ISP serial), 115200 8N1.
// PB10 of the SDK examples is not broken out on this board's headers.

#endif
