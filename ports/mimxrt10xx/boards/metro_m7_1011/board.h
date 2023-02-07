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
#define BOARD_FLASH_SIZE     (8*1024*1024)

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+

#define LED_PINMUX          IOMUXC_GPIO_03_GPIOMUX_IO03
#define LED_PORT            GPIO1
#define LED_PIN             3
#define LED_STATE_ON        1

#define LED_PWM_PINMUX      IOMUXC_GPIO_03_FLEXPWM1_PWM1_B
#define LED_PWM_BASE        PWM1
#define LED_PWM_MODULE      kPWM_Module_1
#define LED_PWM_CHANNEL     kPWM_PwmB

//--------------------------------------------------------------------+
// Neopixel
//--------------------------------------------------------------------+

// Number of neopixels
#define NEOPIXEL_NUMBER     1
#define NEOPIXEL_PINMUX     IOMUXC_GPIO_00_GPIOMUX_IO00
#define NEOPIXEL_PORT       GPIO1
#define NEOPIXEL_PIN        0

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID              0x239A
#define USB_PID              0x00E1
#define USB_MANUFACTURER     "Adafruit"
#define USB_PRODUCT          "Metro M7 iMX RT1011"

#define UF2_PRODUCT_NAME     USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID         "MIMXRT1011-Metro-revA"
#define UF2_VOLUME_LABEL     "METROM7BOOT"
#define UF2_INDEX_URL        "https://www.adafruit.com/product/4950"

//--------------------------------------------------------------------+
// UART
//--------------------------------------------------------------------+

#define UART_DEV              LPUART1
#define UART_RX_PINMUX        IOMUXC_GPIO_09_LPUART1_RXD
#define UART_TX_PINMUX        IOMUXC_GPIO_10_LPUART1_TXD

//--------------------------------------------------------------------+
// ESP32 Co-Processors
//--------------------------------------------------------------------+
#define ESP32_GPIO0_PINMUX    IOMUXC_GPIO_SD_05_GPIO2_IO05
#define ESP32_GPIO0_PORT      GPIO2
#define ESP32_GPIO0_PIN       5

#define ESP32_RESET_PINMUX    IOMUXC_GPIO_AD_07_GPIOMUX_IO21
#define ESP32_RESET_PORT      GPIO1
#define ESP32_RESET_PIN       21


#endif /* BOARD_H_ */
