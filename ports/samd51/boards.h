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

// Initial stack pointer inside SRAM, and reset handler a Thumb address in [start, end)
static inline bool vector_table_valid(uint32_t sp, uint32_t entry, uint32_t start, uint32_t end) {
  return (sp & 3u) == 0 && sp > HSRAM_ADDR && sp <= HSRAM_ADDR + HSRAM_SIZE && (entry & 1u) != 0 && entry >= start &&
         entry < end;
}

// Enable write protection
#ifndef TINYUF2_PROTECT_BOOTLOADER
  #define TINYUF2_PROTECT_BOOTLOADER 1
#endif

// Brightness scale, in 256ths
#ifndef NEOPIXEL_BRIGHTNESS
  #define NEOPIXEL_BRIGHTNESS 0x10
#endif

#ifdef __cplusplus
}
#endif

#endif /* BOARDS_H_ */
