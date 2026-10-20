#ifndef BOARD_H_
#define BOARD_H_

//--------------------------------------------------------------------+
// Button, pulled up and active low. Holding it at reset enters the bootloader
//--------------------------------------------------------------------+
#define BUTTON_PORT         2
#define BUTTON_PIN          11
#define BUTTON_STATE_ACTIVE 0

//--------------------------------------------------------------------+
// Neopixel
//--------------------------------------------------------------------+

// Number of neopixels
#define NEOPIXEL_NUMBER 16
// Brightness percentage from 1 to 255
#define NEOPIXEL_BRIGHTNESS 0x08

#define NEOPIXEL_PORT       1
#define NEOPIXEL_PIN        30

// Neopixel supply enable, STATE is the level that switches it on
#define NEOPIXEL_POWER_PORT  2
#define NEOPIXEL_POWER_PIN   14
#define NEOPIXEL_POWER_STATE 1

//--------------------------------------------------------------------+
// Flash
//--------------------------------------------------------------------+

// Flash size of the board
#define BOARD_FLASH_SIZE 0x100000

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID          0x03EB
#define USB_PID          0x2402
#define USB_MANUFACTURER "Intech Studio"
#define USB_PRODUCT      "Bootloader 2026-10"

#define UF2_PRODUCT_NAME USB_PRODUCT
#define UF2_BOARD_ID     "SAMD51N20A-GRID-v0"
#define UF2_VOLUME_LABEL "GRID26"
#define UF2_INDEX_URL    "https://github.com/intechstudio/grid-fw/"

#endif
