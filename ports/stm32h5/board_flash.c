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

#include "board_api.h"

#ifndef BUILD_NO_TINYUSB
#include "tusb.h"
#endif

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM
//--------------------------------------------------------------------+

#define FLASH_BASE_ADDR         0x08000000UL

// H503 is 1 bit per sector, the rest of the family H523/33/62/63 is 1 bit per 4 sectors
// TinyUF2 resides in the first 8 flash sectors on STM32H5s, therefore these are write protected
#ifdef STM32H503xx
#define BOARD_FLASH_PROTECT_MASK  0x7u // protect 3 sector
#else
#define BOARD_FLASH_PROTECT_MASK  0x1u // protect 1 group of sector 0-3
#endif

// H5 has uniform sector size of 8KB, max is 2MB
enum {
  SECTOR_COUNT = (2*1024*1024) / FLASH_SECTOR_SIZE
};
static uint8_t erased_sectors[SECTOR_COUNT];

//--------------------------------------------------------------------+
// Internal Helper
//--------------------------------------------------------------------+
static bool is_blank(uint32_t addr, uint32_t size) {
  for (uint32_t i = 0; i < size; i += sizeof(uint32_t)) {
    if (*(uint32_t*)(addr + i) != 0xffffffff) {
      return false;
    }
  }
  return true;
}

static bool flash_erase(uint32_t addr) {
  TUF2_ASSERT(addr < FLASH_BASE_ADDR + BOARD_FLASH_SIZE);

  const uint32_t sector_addr = addr & ~(FLASH_SECTOR_SIZE - 1);
  const uint32_t sector_id = (sector_addr - FLASH_BASE_ADDR) / FLASH_SECTOR_SIZE;

  const uint8_t erased = erased_sectors[sector_id];
  erased_sectors[sector_id] = 1; // mark as erased

#ifndef TINYUF2_SELF_UPDATE
  // skip erasing bootloader
  TUF2_ASSERT(sector_addr >= BOARD_FLASH_APP_START);
#endif

  if ( !erased && !is_blank(sector_addr, FLASH_SECTOR_SIZE) ) {
    uint32_t bank;
    uint32_t sector_to_erase;
    const uint32_t sector_per_bank = FLASH_BANK_SIZE / FLASH_SECTOR_SIZE;

    if (sector_id < sector_per_bank) {
      sector_to_erase = sector_id;
      bank = FLASH_BANK_1;
    } else {
      sector_to_erase = sector_id - sector_per_bank;
      bank = FLASH_BANK_2;
    }

    // bank swap
    if (READ_BIT(FLASH->OPTSR_CUR, FLASH_OPTSR_SWAP_BANK)) {
      bank = FLASH_BANK_BOTH - bank;
    }

    FLASH_EraseInitTypeDef erase_struct= {
      .TypeErase     = FLASH_TYPEERASE_SECTORS,
      .Banks         = bank,
      .Sector        = sector_to_erase,
      .NbSectors     = 1
    };

    // FLASH_Erase_Sector(sector, bank);
    // FLASH_WaitForLastOperation(HAL_MAX_DELAY);
    uint32_t sector_error;
    TUF2_LOG1("Erase: %08lX size = %lu KB, bank = %lu ... ", sector_addr, FLASH_SECTOR_SIZE / 1024, bank);
    TUF2_ASSERT(HAL_OK ==HAL_FLASHEx_Erase(&erase_struct, &sector_error));
    (void) sector_error;

    TUF2_LOG1("OK\r\n");
    TUF2_ASSERT( is_blank(sector_addr, FLASH_SECTOR_SIZE) );
  }

  return true;
}

static void flash_write(uint32_t dst, const uint8_t* src, int len) {
  flash_erase(dst);

  TUF2_LOG1("Write flash at address %08lX\r\n", dst);
  for (int i = 0; i < len; i += 16) {
    if (HAL_FLASH_Program(FLASH_TYPEPROGRAM_QUADWORD, dst + i, (uint32_t)src + i) != HAL_OK) {
      TUF2_LOG1("Failed to write flash at address %08lX\r\n", dst + i);
      break;
    }
  }

  // verify contents
  if (memcmp((void*)dst, src, len) != 0) {
    TUF2_LOG1("Failed to write\r\n");
  }
}

//--------------------------------------------------------------------+
// Board API
//--------------------------------------------------------------------+
void board_flash_init(void) {
  memset(erased_sectors, 0, sizeof(erased_sectors));
}

uint32_t board_flash_size(void) {
  return BOARD_FLASH_SIZE;
}

void board_flash_read(uint32_t addr, void* buffer, uint32_t len) {
  memcpy(buffer, (void*)addr, len);
}

void board_flash_flush(void) {
}

bool board_flash_write(uint32_t addr, void const* data, uint32_t len) {
  // TODO skip matching contents need to compare a whole sector
  HAL_FLASH_Unlock();
  flash_write(addr, data, len);
  HAL_FLASH_Lock();
  return true;
}

void board_flash_erase_app(void) {
  // erase 1st sector of app region is enough to invalid the app
  flash_erase(BOARD_FLASH_APP_START);
}

bool board_flash_protect_bootloader(bool protect) {
  bool ret = true;

  HAL_FLASH_OB_Unlock();

  FLASH_OBProgramInitTypeDef ob_current = {0};
  HAL_FLASHEx_OBGetConfig(&ob_current);

  // Flash sectors are protected if the bit is cleared
  bool const already_protected = (ob_current.WRPSector & BOARD_FLASH_PROTECT_MASK) == 0;

  TUF2_LOG1("Protection: current = %u, request = %u\r\n", already_protected, protect);

  // request and current state mismatched --> require ob program
  if (protect != already_protected) {
    FLASH_OBProgramInitTypeDef ob_update = { 0 };
    ob_update.OptionType = OPTIONBYTE_WRP;
    ob_update.Banks = FLASH_BANK_1;
    ob_update.WRPSector = BOARD_FLASH_PROTECT_MASK;
    ob_update.WRPState = protect ? OB_WRPSTATE_ENABLE : OB_WRPSTATE_DISABLE;

    if (HAL_FLASHEx_OBProgram(&ob_update) == HAL_OK) {
      HAL_FLASH_OB_Launch();
    } else {
      ret = false;
    }
  }

  HAL_FLASH_OB_Lock();

  return ret;
}

#ifdef TINYUF2_SELF_UPDATE

bool is_new_bootloader_valid(const uint8_t* bootloader_bin, uint32_t bootloader_len) {
  // at least larger than vector table
  if (bootloader_len < 1024) return false;

  // similar to board_app_valid() check
  uint32_t const* app_vector = (uint32_t const*) (uintptr_t) bootloader_bin;
  uint32_t sp = app_vector[0];
  uint32_t boot_entry = app_vector[1];

  // 1st word is stack pointer (must be in SRAM region)
  if ((sp & 0xff000003) != 0x20000000) return false;

  // 2nd word is App entry point (reset), must smaller than app start
  if (boot_entry >= BOARD_FLASH_APP_START) {
    return false;
  }

  return true;
}

void board_self_update(const uint8_t* bootloader_bin, uint32_t bootloader_len) {
  // check if the bootloader payload is valid
  if (is_new_bootloader_valid(bootloader_bin, bootloader_len)) {
    #if TINYUF2_PROTECT_BOOTLOADER
    // Note: Don't protect bootloader when done, leave that to the new bootloader
    // since it may or may not enable protection.
    board_flash_protect_bootloader(false);
    #endif

    // keep writing until flash contents matches new bootloader data
    while (memcmp((const void*)FLASH_BASE_ADDR, bootloader_bin, bootloader_len)) {
      uint32_t sector_addr = FLASH_BASE_ADDR;
      const uint8_t* data = bootloader_bin;
      uint32_t len = bootloader_len;

      for (uint32_t i = 0; i < 4 && len > 0; i++) {
        uint32_t const size = (FLASH_SECTOR_SIZE < len ? FLASH_SECTOR_SIZE : len);
        board_flash_write(sector_addr, data, size);

        sector_addr += size;
        data += size;
        len -= size;
      }
    }
  }

  // self-destruct: write 0 to first 2 entry of vector table
  // Note: write bit from 1 to 0 does not need to erase in advance
  __disable_irq();
  HAL_FLASH_Unlock();

  uint32_t null_arr[4] = { 0 };
  HAL_FLASH_Program(FLASH_TYPEPROGRAM_QUADWORD, BOARD_FLASH_APP_START, (uint32_t)null_arr);

  HAL_FLASH_Lock();

  // reset to run new bootloader
  NVIC_SystemReset();
}
#endif
