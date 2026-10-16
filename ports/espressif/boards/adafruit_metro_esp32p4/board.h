/*
 * SPDX-FileCopyrightText: 2026 Adafruit Industries LLC
 * SPDX-License-Identifier: MIT
 */
#ifndef ADAFRUIT_METRO_ESP32P4_H_
#define ADAFRUIT_METRO_ESP32P4_H_

#define PIN_BUTTON_UF2                   35

// BAT_SENSE: 1 Mohm / 1 Mohm divider, with CBATRAW changed to 2.2 uF.
// The bootloader temporarily charges this capacitor above VBAT/2.
#define PIN_DOUBLE_RESET_ADC             18
#define BOARD_DOUBLE_RESET_ADC_CHANNEL   2
#define BOARD_DOUBLE_RESET_ADC_THRESHOLD_MV 2500

#define NEOPIXEL_PIN                     23
#define NEOPIXEL_BRIGHTNESS              0x10
#define NEOPIXEL_NUMBER                  1
#define LED_PIN                          13
#define LED_STATE_ON                     1

// USB-C uses the Serial/JTAG pins, GPIO24/25, with the FS OTG PHY swapped in.
#define BOARD_USB_FS_PHY_SWAP            1

#define USB_VID                          0x239A
#define USB_PID                          0x017B
#define USB_MANUFACTURER                 "Adafruit"
#define USB_PRODUCT                      "Metro ESP32-P4"
#define UF2_PRODUCT_NAME                 USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID                     "ESP32P4-Metro-revA"
#define UF2_VOLUME_LABEL                 "METROP4BOOT"
#define UF2_INDEX_URL                    "https://www.adafruit.com"
#define TINYUF2_FAVICON_HEADER            "favicon_adafruit_256.h"

#endif
