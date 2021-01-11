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

// ISP button
#define BUTTON_PORT           0
#define BUTTON_PIN            5
#define BUTTON_STATE_ACTIVE   0

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+

#define LED_PORT              0
#define LED_PIN               1
#define LED_STATE_ON          1

//--------------------------------------------------------------------+
// RGB
//--------------------------------------------------------------------+

#define NEOPIXEL_NUMBER       0

// RGB pins are P1_6, P1_7, P1_4
#define LED_TRICOLOR_GPIO     { {1, 6}, {1, 7}, {1, 4} }
#define LED_TRICOLO_ON        0

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
#define UF2_INDEX_URL     "https://www.nxp.com/LPC55S28-EVK"

//--------------------------------------------------------------------+
// Flash
//--------------------------------------------------------------------+

#define BOARD_FLASH_SIZE     (0x80000U)

//--------------------------------------------------------------------+
// UART
//--------------------------------------------------------------------+

#define UART_DEV              USART0
#define UART_RX_IOMUX         0U, 29U, IOCON_PIO_DIG_FUNC1_EN
#define UART_TX_IOMUX         0U, 30U, IOCON_PIO_DIG_FUNC1_EN

#endif
