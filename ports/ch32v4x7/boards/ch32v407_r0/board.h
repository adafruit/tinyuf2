// SPDX-License-Identifier: MIT
#pragma once
// LED1 reaches the MCU only through header P1: jumper it to PC0 (CH32V4x7SCH, CH32V407VET6-EVT-R0)
#define LED_PORT         GPIOC
#define LED_PIN          GPIO_Pin_0
#define LED_STATE_ON     0
#define LED_CLOCK        RCC_PB2Periph_GPIOC
// the Metro CH32V407's bootloader IDs: a development board, no allocation of its own
#define USB_VID          0x239a
#define USB_PID          0x017d
#define USB_MANUFACTURER "WCH"
#define USB_PRODUCT      "CH32V407 EVT TinyUF2"
#define UF2_PRODUCT_NAME USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID     "CH32V407-EVT-R0"
#define UF2_VOLUME_LABEL "V407EVT"
#define UF2_INDEX_URL    "https://www.wch-ic.com/products/CH32V407.html"
