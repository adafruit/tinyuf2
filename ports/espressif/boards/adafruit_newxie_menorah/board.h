// SPDX-FileCopyrightText: 2026 Adafruit Industries
// SPDX-License-Identifier: MIT

#ifndef ADAFRUIT_NEWXIE_MENORAH_H_
#define ADAFRUIT_NEWXIE_MENORAH_H_

// Press BOOT during the purple reset window to enter TinyUF2. Holding BOOT
// while resetting instead enters the ESP32-S3 ROM downloader.
#define PIN_BUTTON_UF2 0

// This board has no double-reset RC circuit or NeoPixel power-enable pin.
#define NEOPIXEL_PIN        42
#define NEOPIXEL_BRIGHTNESS 0x10
#define NEOPIXEL_NUMBER     1

// Optional 135 x 240 ST7789 Newxie in socket J1. The display is write-only;
// USB and the NeoPixel work normally when no display is plugged in.
#define CONFIG_LCD_TYPE_ST7789V
#define DISPLAY_PIN_MISO -1
#define DISPLAY_PIN_MOSI 33
#define DISPLAY_PIN_SCK  34
#define DISPLAY_PIN_CS   41
#define DISPLAY_PIN_DC   15
#define DISPLAY_PIN_RST  -1
#define DISPLAY_PIN_BL   46
#define DISPLAY_BL_ON    1

// Use the existing landscape TinyUF2 screen on the portrait plug-in panel.
#define DISPLAY_WIDTH          240
#define DISPLAY_HEIGHT         135
#define DISPLAY_COL_OFFSET     53
#define DISPLAY_ROW_OFFSET     40
#define DISPLAY_MADCTL         (TFT_MADCTL_MX)
#define DISPLAY_VSCSAD         0
#define DISPLAY_TITLE          "Menorah"

#define USB_VID                0x239A
#define USB_PID                0x0181
#define USB_MANUFACTURER       "Adafruit"
#define USB_PRODUCT            "Newxie Menorah ESP32-S3"

#define UF2_PRODUCT_NAME       USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID           "ESP32S3-NewxieMenorah-revA"
#define UF2_VOLUME_LABEL       "NEWXIEBOOT"
#define UF2_INDEX_URL          "https://www.adafruit.com/"
#define TINYUF2_FAVICON_HEADER "favicon_adafruit_256.h"

#endif
