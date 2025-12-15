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
 */

#ifndef BOARD_H_
#define BOARD_H_

// Size of on-board external flash
#define BOARD_FLASH_SIZE      (16*1024*1024)

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+

#define LED_PINMUX            IOMUXC_GPIO_AD_04_GPIO9_IO03
#define LED_PORT              GPIO9
#define LED_PIN               3
#define LED_STATE_ON          1

//--------------------------------------------------------------------+
// Neopixel
//--------------------------------------------------------------------+

// Number of neopixels
#define NEOPIXEL_NUMBER       0

//--------------------------------------------------------------------+
// Button
//--------------------------------------------------------------------+

// SW7 button on WAKEUP pin
#define BUTTON_PINMUX         IOMUXC_WAKEUP_DIG_GPIO13_IO00
#define BUTTON_PORT           GPIO13
#define BUTTON_PIN            0
#define BUTTON_STATE_ACTIVE   0

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID           0x239A
#define USB_PID           0x0099
#define USB_MANUFACTURER  "NXP"
#define USB_PRODUCT       "RT1170 EVK"

#define UF2_PRODUCT_NAME  USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID      "MIMXRT1170-EVKB-revB"
#define UF2_VOLUME_LABEL  "RT1170BOOT"
#define UF2_INDEX_URL     "https://www.nxp.com/part/MIMXRT1170-EVK#/"

//--------------------------------------------------------------------+
// USB PHY
//--------------------------------------------------------------------+

#define BOARD_USB_PHY_D_CAL     (0x07U)
#define BOARD_USB_PHY_TXCAL45DP (0x06U)
#define BOARD_USB_PHY_TXCAL45DM (0x06U)

//--------------------------------------------------------------------+
// UART
//--------------------------------------------------------------------+

#define UART_DEV              LPUART1
#define UART_RX_PINMUX        IOMUXC_GPIO_AD_25_LPUART1_RXD
#define UART_TX_PINMUX        IOMUXC_GPIO_AD_24_LPUART1_TXD

#endif /* BOARD_H_ */
