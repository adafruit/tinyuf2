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

#define FLASH_BASE_ADDR   0x08000000UL

enum
{
  SECTOR_COUNT = 2048/4
};

static uint8_t erased_sectors[SECTOR_COUNT] = { 0 };

//--------------------------------------------------------------------+
// Internal Helper
//--------------------------------------------------------------------+

static inline uint32_t flash_sector_size(uint32_t sector)
{
  (void) sector;
  return BOARD_PAGE_SIZE;
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

  TUF2_ASSERT(sector);

  if ( !erased && !is_blank(sector_addr, size) )
  {
    TUF2_LOG1("Erase: %08lX size = %lu KB ... ", sector_addr, size / 1024);

    FLASH_EraseInitTypeDef EraseInit = {};
    EraseInit.TypeErase = TYPEERASE_PAGES;
    EraseInit.Banks = FLASH_BANK_1;
    EraseInit.Page = sector;
    EraseInit.NbPages = 1;

    // erase the sector
    uint32_t SectorError = 0;
    HAL_FLASHEx_Erase(&EraseInit, &SectorError);
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
  for ( int i = 0; i < len; i += 8 )
  {
    uint64_t data = *((uint64_t*) ((void*) (src + i)));

    if ( HAL_FLASH_Program(FLASH_TYPEPROGRAM_DOUBLEWORD, dst + i, data) != HAL_OK )
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
  if (memcmp((void*)dst, src, len) != 0)
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

#ifdef TINYUF2_SELF_UPDATE
/**
 * This will require enabling dual boot mode, making a backup and then copying
 */
void board_self_update(const uint8_t * bootloader_bin, uint32_t bootloader_len)
{
  (void) bootloader_bin;
  (void) bootloader_len;
}
#endif
