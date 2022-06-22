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
#include "tusb.h" // for logging

#define FLASH_CACHE_SIZE          512
#define FLASH_CACHE_INVALID_ADDR  0xffffffff

//--------------------------------------------------------------------+
//define flash space, reserve first 8 sectors for bootloader up to 3FFF
//--------------------------------------------------------------------+

#define BOARD_FLASH_SECTORS 64
#define BOARD_FIRST_FLASH_SECTOR_TO_ERASE 8

#define APP_LOAD_ADDRESS 0x08004000

/* flash parameters */
#define SIZE 2048

static uint8_t erasedSectors[BOARD_FLASH_SECTORS];

uint32_t flash_func_sector_size(unsigned sector)
{
  if (sector < BOARD_FLASH_SECTORS) {
    return SIZE;
  }

  return 0;
}

static bool is_blank(uint32_t addr, uint32_t size)
{
  for (uint32_t i = 0; i < size; i += sizeof(uint32_t)) {
    if (*(uint32_t*)(addr + i) != 0xffffffff) {
      return false;
    }
  }
  return true;
}

                    //ADDR            data
void flash_write(uint32_t dst, const uint8_t *src, int len)
{
   // assume sector 0-7 (bootloader) is same size as sector 1
  uint32_t addr = APP_LOAD_ADDRESS;
  uint32_t sector = 0;
  int erased = false;
  uint32_t size = 0;

  for ( unsigned i = 0; i < BOARD_FLASH_SECTORS; i++ )
  {
    size = flash_func_sector_size(i);
    if ( addr + size > dst )
    {
      sector = i + 1;
      erased = erasedSectors[i];
      erasedSectors[i] = 1;    // don't erase anymore - we will continue writing here!
      break;
    }
    addr += size;
  }

  if (sector == 0)
  {
    TU_LOG1("invalid sector\r\n");
  }

  HAL_FLASH_Unlock();

  if (!erased && !is_blank(addr, size))
  {
    uint32_t SectorError = 0;

    TU_LOG1("Erase: %08lX size = %lu\n", addr, size);

    FLASH_EraseInitTypeDef EraseInit;
    EraseInit.TypeErase = FLASH_TYPEERASE_PAGES;
    EraseInit.PageAddress = addr;
    EraseInit.NbPages = ((0x08040000 - addr)/size);

    HAL_FLASHEx_Erase(&EraseInit, &SectorError);
    FLASH_WaitForLastOperation(HAL_MAX_DELAY);

    if (SectorError != 0xFFFFFFFF)
    {
      TU_LOG1("failed to erase!\r\n");
    }
  }

  for (int i = 0; i < len; i += 4)
  {
    uint32_t data = *( (uint32_t*) ((void*) (src + i)) );
    HAL_FLASH_Program(FLASH_TYPEPROGRAM_WORD, dst + i, (uint64_t) data);
  }

  if (memcmp((void*)dst, src, len) != 0)
  {
    TU_LOG1("failed to write\r\n");
  }
}

//--------------------------------------------------------------------+
//
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
void board_flash_write (uint32_t addr, void const *data, uint32_t len)
{
  // TODO skip matching contents
  flash_write(addr, data, len);
}

void board_flash_erase_app(void)
{
  // TODO implement later
}

bool board_flash_protect_bootloader(bool protect)
{
  // TODO implement later
  (void) protect;
  return false;
}

#ifdef TINYUF2_SELF_UPDATE
void board_self_update(const uint8_t * bootloader_bin, uint32_t bootloader_len)
{
  (void) bootloader_bin;
  (void) bootloader_len;
}
#endif
