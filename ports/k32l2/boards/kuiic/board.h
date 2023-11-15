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

#include "kuiic_rgb.h"

//--------------------------------------------------------------------+
// Flash
//--------------------------------------------------------------------+

#define BOARD_FLASH_SIZE      0x40000U

//--------------------------------------------------------------------+
// KUIIC RGB LED
//--------------------------------------------------------------------+

#define KUIIC_RGB_LED         1

//--------------------------------------------------------------------+
// Neopixel
//--------------------------------------------------------------------+

// Number of neopixels
#define NEOPIXEL_NUMBER       0

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

// 0x1FC9, 0x0154 is reserved for TinyUF2 usage
#define USB_VID           0x1FC9
#define USB_PID           0x0154
#define USB_MANUFACTURER  "NXP"
#define USB_PRODUCT       "KUIIC"

#define UF2_PRODUCT_NAME  USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID      "KUIIC"
#define UF2_VOLUME_LABEL  "K32L2BOOT"
#define UF2_INDEX_URL     "https://www.nxp.com/docs/en/data-sheet/K32L2B3x.pdf"

//--------------------------------------------------------------------+
// UART
//--------------------------------------------------------------------+

#define UART_DEV              LPUART1
#define UART_SET_CLOCK        CLOCK_SetLpuart1Clock(1)
#define UART_CLK_PORT         kCLOCK_PortE
#define UART_PIN_PORT         PORTE
#define UART_TX_PIN           0
#define UART_TX_MUX           kPORT_MuxAlt3
// PTE1 is not connected in this package
// but RX is not needed to output log messages
#define UART_RX_PIN           1
#define UART_RX_MUX           kPORT_MuxAlt3
#define UART_SOPT_INIT        \
  SIM->SOPT5 &= ~(SIM_SOPT5_LPUART1TXSRC_MASK | SIM_SOPT5_LPUART1RXSRC_MASK)

#endif
