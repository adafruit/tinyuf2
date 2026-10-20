#ifndef BOARDS_H_
#define BOARDS_H_

#ifdef __cplusplus
extern "C" {
#endif

#include "sam.h"

#include "board.h"

#define BOARD_FLASH_ADDR_ZERO 0x00000000

// Flash Start Address of Application
#ifndef BOARD_FLASH_APP_START
extern uint32_t __flash_boot_size[];
  #define BOARD_FLASH_APP_START (BOARD_FLASH_ADDR_ZERO + (uint32_t)__flash_boot_size)
#endif

// Enable write protection
#ifndef TINYUF2_PROTECT_BOOTLOADER
  #define TINYUF2_PROTECT_BOOTLOADER 1
#endif

// Brightness percentage from 1 to 255
#ifndef NEOPIXEL_BRIGHTNESS
  #define NEOPIXEL_BRIGHTNESS 0x10
#endif

#ifdef __cplusplus
}
#endif

#endif /* BOARDS_H_ */
