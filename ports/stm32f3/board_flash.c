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

#define FLASH_CACHE_SIZE          4096
#define FLASH_CACHE_INVALID_ADDR  0xffffffff

//--------------------------------------------------------------------+
//
//--------------------------------------------------------------------+

#define BOARD_FLASH_SECTORS 8
#define BOARD_FIRST_FLASH_SECTOR_TO_ERASE 0

#define APP_LOAD_ADDRESS 0x08010000

/* flash parameters that we should not really know */
static struct {
	uint32_t	sector_number;
	uint32_t	size;
} flash_sectors[] = {

	/* Physical FLASH sector 0 is reserved for bootloader and is not
	 * the table below.
	 * N sectors may aslo be reserved for the app fw in which case
	 * the zero based define BOARD_FIRST_FLASH_SECTOR_TO_ERASE must
	 * be defined to begin the erase above of the reserved sectors.
	 * The default value of BOARD_FIRST_FLASH_SECTOR_TO_ERASE is 0
	 * and begins flash erase operations at phsical sector 1 the 0th entry
	 * in the table below.
	 * A value of 1 for BOARD_FIRST_FLASH_SECTOR_TO_ERASE would reserve
	 * the 0th entry and begin erasing a index 1 the third physical sector
	 * on the device.
	 *
	 * When BOARD_FIRST_FLASH_SECTOR_TO_ERASE is defined APP_RESERVATION_SIZE
	 * must also be defined to remove that additonal reserved FLASH space
	 * from the BOARD_FLASH_SIZE. See APP_SIZE_MAX below.
	 */

	{0x01, 16 * 1024},
	{0x02, 16 * 1024},
	{0x03, 16 * 1024},
	{0x04, 64 * 1024},
	{0x05, 128 * 1024},
	{0x06, 128 * 1024},
	{0x07, 128 * 1024},
	{0x08, 128 * 1024},
	{0x09, 128 * 1024},
	{0x0a, 128 * 1024},
	{0x0b, 128 * 1024},
	/* flash sectors only in 2MiB devices */
	{0x10, 16 * 1024},
	{0x11, 16 * 1024},
	{0x12, 16 * 1024},
	{0x13, 16 * 1024},
	{0x14, 64 * 1024},
	{0x15, 128 * 1024},
	{0x16, 128 * 1024},
	{0x17, 128 * 1024},
	{0x18, 128 * 1024},
	{0x19, 128 * 1024},
	{0x1a, 128 * 1024},
	{0x1b, 128 * 1024},
};

static uint8_t erasedSectors[BOARD_FLASH_SECTORS];

uint32_t flash_func_sector_size(unsigned sector)
{
	if (sector < BOARD_FLASH_SECTORS) {
		return flash_sectors[sector].size;
	}

	return 0;
}

static bool is_blank(uint32_t addr, uint32_t size) {
		for (uint32_t i = 0; i < size; i += sizeof(uint32_t)) {
			if (*(uint32_t*)(addr + i) != 0xffffffff) {
				return false;
			}
		}
		return true;
}

void flash_write(uint32_t dst, const uint8_t *src, int len)
{
	// assume sector 0 (bootloader) is same size as sector 1
	uint32_t addr = flash_func_sector_size(0) + (APP_LOAD_ADDRESS & 0xfff00000);
	uint32_t sector = 0;
	int erased = false;
	uint32_t size = 0;

  for ( unsigned i = 0; i < BOARD_FLASH_SECTORS; i++ )
  {
    size = flash_func_sector_size(i);
    if ( addr + size > dst )
    {
      sector = flash_sectors[i].sector_number;
      erased = erasedSectors[i];
      erasedSectors[i] = 1;    // don't erase anymore - we will continue writing here!
      break;
    }
    addr += size;
  }

	if (sector == 0)
	{
	  TU_LOG1("invalid sector");
	}

	HAL_FLASH_Unlock();

	if (!erased && !is_blank(addr, size))
	{
	  TU_LOG1("Erase: %08lX size = %lu\n", addr, size);

		FLASH_Erase_Sector(sector, FLASH_VOLTAGE_RANGE_3);
		FLASH_WaitForLastOperation(HAL_MAX_DELAY);

		if (!is_blank(addr, size))
		{
		  TU_LOG1("failed to erase!");
		}
	}

	for (int i = 0; i < len; i += 4)
	{
	  HAL_FLASH_Program(FLASH_TYPEPROGRAM_WORD, dst + i, (uint64_t) (*(uint32_t*)(src + i)) );
	}

	if (memcmp((void*)dst, src, len) != 0)
	{
	  TU_LOG1("failed to write");
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


#ifdef TINYUF2_SELF_UPDATE
void board_self_update(const uint8_t * bootloader_bin, uint32_t bootloader_len)
{
  (void) bootloader_bin;
  (void) bootloader_len;
}
#endif
