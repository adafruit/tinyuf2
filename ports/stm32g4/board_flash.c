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

// TinyUF2 resides in the first 2 flash sectors on STM32F4s, therefore these are write protected
#define BOOTLOADER_SECTOR_MASK  0x3UL

/* flash parameters that we should not really know */
static const uint32_t sector_size[] =
{
  // First 4 sectors are for bootloader (64KB)
  16 * 1024,
	16 * 1024,
	16 * 1024,
	16 * 1024,
	// Application (BOARD_FLASH_APP_START)
	64 * 1024,
	128 * 1024,
	128 * 1024,
	128 * 1024,

	// flash sectors only in 1 MB devices
	128 * 1024,
	128 * 1024,
	128 * 1024,
	128 * 1024,

	// flash sectors only in 2 MB devices
	16 * 1024,
	16 * 1024,
	16 * 1024,
	16 * 1024,
	64 * 1024,
	128 * 1024,
	128 * 1024,
	128 * 1024,
	128 * 1024,
	128 * 1024,
	128 * 1024,
	128 * 1024
};

enum
{
  SECTOR_COUNT = sizeof(sector_size)/sizeof(sector_size[0])
};

static uint8_t erased_sectors[SECTOR_COUNT] = { 0 };

//--------------------------------------------------------------------+
// Internal Helper
//--------------------------------------------------------------------+

static inline uint32_t flash_sector_size(uint32_t sector)
{
  return sector_size[sector];
}

static bool is_blank(uint32_t addr, uint32_t size)
{
  for ( uint32_t i = 0; i < size; i += sizeof(uint32_t) )
  {
    if ( *(uint32_t*) (addr + i) != 0xffffffff )
    {
      return false;
    }
  }
  return true;
}

static bool flash_erase(uint32_t addr)
{
  // starting address from 0x08000000
  uint32_t sector_addr = FLASH_BASE_ADDR;
  bool erased = false;

  uint32_t sector = 0;
  uint32_t size = 0;

  for ( uint32_t i = 0; i < SECTOR_COUNT; i++ )
  {
    TUF2_ASSERT(sector_addr < FLASH_BASE_ADDR + BOARD_FLASH_SIZE);

    size = flash_sector_size(i);
    if ( sector_addr + size > addr )
    {
      sector = i;
      erased = erased_sectors[i];
      erased_sectors[i] = 1;    // don't erase anymore - we will continue writing here!
      break;
    }
    sector_addr += size;
  }

#ifndef TINYUF2_SELF_UPDATE
  // skip erasing sector0 if not self-update
  TUF2_ASSERT(sector);
#endif

  if ( !erased && !is_blank(sector_addr, size) )
  {
    TUF2_LOG1("Erase: %08lX size = %lu KB ... ", sector_addr, size / 1024);
    FLASH_Erase_Sector(sector, FLASH_VOLTAGE_RANGE_3);
    FLASH_WaitForLastOperation(HAL_MAX_DELAY);
    TUF2_LOG1("OK\r\n");
    TUF2_ASSERT( is_blank(sector_addr, size) );
  }

  return true;
}

static void flash_write(uint32_t dst, const uint8_t *src, int len)
{
  flash_erase(dst);

  TUF2_LOG1("Write flash at address %08lX\r\n", dst);
  for ( int i = 0; i < len; i += 4 )
  {
    uint32_t data = *((uint32_t*) ((void*) (src + i)));

    if ( HAL_FLASH_Program(FLASH_TYPEPROGRAM_WORD, dst + i, (uint64_t) data) != HAL_OK )
    {
      TUF2_LOG1("Failed to write flash at address %08lX\r\n", dst + i);
      break;
    }

    if ( FLASH_WaitForLastOperation(HAL_MAX_DELAY) != HAL_OK )
    {
      TUF2_LOG1("Waiting on last operation failed\r\n");
      return;
    }
  }

  // verify contents
  if ( memcmp((void*) dst, src, len) != 0 )
  {
    TUF2_LOG1("Failed to write\r\n");
  }
}

//--------------------------------------------------------------------+
// Board API
//--------------------------------------------------------------------+
void board_flash_init(void)
{

}

uint32_t board_flash_size(void)
{
  return BOARD_FLASH_SIZE;
}

void board_flash_read(uint32_t addr, void* buffer, uint32_t len)
{
  memcpy(buffer, (void*) addr, len);
}

void board_flash_flush(void)
{
}

// TODO not working quite yet
bool board_flash_write(uint32_t addr, void const* data, uint32_t len)
{
  // TODO skip matching contents
  HAL_FLASH_Unlock();
  flash_write(addr, data, len);
  HAL_FLASH_Lock();

  return true;
}

void board_flash_erase_app(void)
{
  // TODO implement later
}

bool board_flash_protect_bootloader(bool protect)
{
  bool ret = true;

  HAL_FLASH_OB_Unlock();

  FLASH_OBProgramInitTypeDef ob_current = {0};
  HAL_FLASHEx_OBGetConfig(&ob_current);

  // Flash sectors are protected if the bit is cleared
  bool const already_protected = (ob_current.WRPSector & BOOTLOADER_SECTOR_MASK) == 0;

  TUF2_LOG1("Protection: current = %u, request = %u\r\n", already_protected, protect);

  // request and current state mismatched --> require ob program
  if (protect != already_protected)
  {
    FLASH_OBProgramInitTypeDef ob_update = {0};
    ob_update.OptionType = OPTIONBYTE_WRP;
    ob_update.Banks      = FLASH_BANK_1;
    ob_update.WRPSector  = BOOTLOADER_SECTOR_MASK;
    ob_update.WRPState   = protect ? OB_WRPSTATE_ENABLE : OB_WRPSTATE_DISABLE;

    if (HAL_FLASHEx_OBProgram(&ob_update) == HAL_OK)
    {
      HAL_FLASH_OB_Launch();
    }else
    {
      ret = false;
    }
  }

  HAL_FLASH_OB_Lock();

  return ret;
}

#ifdef TINYUF2_SELF_UPDATE

bool is_new_bootloader_valid(const uint8_t * bootloader_bin, uint32_t bootloader_len)
{
  // at least larger than vector table
  if (bootloader_len < 512 ) return false;

  // similar to board_app_valid() check
  uint32_t const * app_vector = (uint32_t const*) bootloader_bin;
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

void board_self_update(const uint8_t * bootloader_bin, uint32_t bootloader_len)
{
  // check if the bootloader payload is valid
  if ( is_new_bootloader_valid(bootloader_bin, bootloader_len) )
  {
#if TINYUF2_PROTECT_BOOTLOADER
    // Note: Don't protect bootloader when done, leave that to the new bootloader
    // since it may or may not enable protection.
    board_flash_protect_bootloader(false);
#endif

    // keep writing until flash contents matches new bootloader data
    while( memcmp((const void*) FLASH_BASE_ADDR, bootloader_bin, bootloader_len) )
    {
      uint32_t sector_addr = FLASH_BASE_ADDR;
      const uint8_t * data = bootloader_bin;
      uint32_t len = bootloader_len;

      for ( uint32_t i = 0; i < 4 && len > 0; i++ )
      {
        uint32_t const size = (flash_sector_size(i) < len ? flash_sector_size(i) : len);
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

  HAL_FLASH_Program(FLASH_TYPEPROGRAM_WORD, BOARD_FLASH_APP_START , 0);
  HAL_FLASH_Program(FLASH_TYPEPROGRAM_WORD, BOARD_FLASH_APP_START+4, 0);

  HAL_FLASH_Lock();

  // reset to run new bootloader
  NVIC_SystemReset();
}
#endif
