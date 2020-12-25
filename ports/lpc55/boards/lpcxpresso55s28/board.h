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

// RGB pins are P1_6, P1_7, P1_4
#define LED_PORT              1
#define LED_PIN               6
#define LED_STATE_ON          0

//--------------------------------------------------------------------+
// Neopixel
//--------------------------------------------------------------------+

// Number of neopixels
#define NEOPIXEL_NUMBER       1
#define NEOPIXEL_PORT         GPIOC
#define NEOPIXEL_PIN          GPIO_PIN_0

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID           0x1fc9
#define USB_PID           0x0094
#define USB_MANUFACTURER  "NXP"
#define USB_PRODUCT       "LPCXpresso 55s28"

#define UF2_PRODUCT_NAME  USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID      "LPC55S28-Xpresso-revA"
#define UF2_VOLUME_LABEL  "LPC5528BOOT"
#define UF2_INDEX_URL     "https://www.nxp.com/design/software/development-software/lpcxpresso55s28-development-board:LPC55S28-EVK"

//--------------------------------------------------------------------+
// UART
//--------------------------------------------------------------------+

#define UART_DEV              USART3
#define UART_CLOCK_ENABLE     __HAL_RCC_USART3_CLK_ENABLE
#define UART_GPIO_PORT        GPIOB
#define UART_GPIO_AF          GPIO_AF7_USART3
#define UART_TX_PIN           GPIO_PIN_10
#define UART_RX_PIN           GPIO_PIN_11

#endif
