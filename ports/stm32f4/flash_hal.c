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
#include "stm32f4xx_hal_flash.h"

#define FLASH_CACHE_SIZE          4096
#define FLASH_CACHE_INVALID_ADDR  0xffffffff

//--------------------------------------------------------------------+
//
//--------------------------------------------------------------------+
#define DMESG(...) ((void)0)
#define PANIC(msg) do { DMESG("PANIC! %s", msg); for(;;); } while (0)

#define BOARD_FLASH_SECTORS 8
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

uint32_t
flash_func_sector_size(unsigned sector)
{
	if (sector < BOARD_FLASH_SECTORS) {
		return flash_sectors[sector].size;
	}

	return 0;
}

static uint8_t erasedSectors[BOARD_FLASH_SECTORS];

static bool is_blank(uint32_t addr, uint32_t size) {
		for (unsigned i = 0; i < size; i += sizeof(uint32_t)) {
			if (*(uint32_t*)(addr + i) != 0xffffffff) {
				DMESG("non blank: %p i=%d/%d", addr, i, size);
				return false;
			}
		}
		return true;
}

void
flash_write(uint32_t dst, const uint8_t *src, int len)
{
	// assume sector 0 (bootloader) is same size as sector 1
	uint32_t addr = flash_func_sector_size(0) + (APP_LOAD_ADDRESS & 0xfff00000);
	uint32_t sector = 0;
	int erased = false;
	uint32_t size = 0;

	for (unsigned i = 0; i < BOARD_FLASH_SECTORS; i++) {
		size = flash_func_sector_size(i);
		if (addr + size > dst) {
			sector = flash_sectors[i].sector_number;
			erased = erasedSectors[i];
			erasedSectors[i] = 1; // don't erase anymore - we will continue writing here!
			break;
		}
		addr += size;
	}

	if (sector == 0)
		PANIC("invalid sector");


    flash_unlock();

	if (!erased && !is_blank(addr, size)) {
		flash_erase_sector(sector, FLASH_CR_PROGRAM_X32);
		if (!is_blank(addr, size))
			PANIC("failed to erase!");
	}

    for (int i = 0; i < len; i += 4) {
		flash_program_word(dst + i, *(uint32_t*)(src + i));
    }

	if (memcmp((void*)dst, src, len) != 0)
		PANIC("failed to write");
}

void
flash_func_erase_sector(unsigned sector)
{
	if (sector >= BOARD_FLASH_SECTORS || sector < BOARD_FIRST_FLASH_SECTOR_TO_ERASE) {
		return;
	}

	/* Caculate the logical base address of the sector
	 * flash_func_read_word will add APP_LOAD_ADDRESS
	 */
	uint32_t address = 0;

	for (unsigned i = BOARD_FIRST_FLASH_SECTOR_TO_ERASE; i < sector; i++) {
		address += flash_func_sector_size(i);
	}

	/* blank-check the sector */
	unsigned size = flash_func_sector_size(sector);
	bool blank = true;

	for (unsigned i = 0; i < size; i += sizeof(uint32_t)) {
		if (flash_func_read_word(address + i) != 0xffffffff) {
			blank = false;
			break;
		}
	}

	/* erase the sector if it failed the blank check */
	if (!blank) {
		flash_erase_sector(flash_sectors[sector].sector_number, FLASH_CR_PROGRAM_X32);
	}
}

void
flash_func_write_word(uint32_t address, uint32_t word)
{
	flash_program_word(address + APP_LOAD_ADDRESS, word);
}

uint32_t
flash_func_read_word(uint32_t address)
{
	if (address & 3) {
		return 0;
	}

	return *(uint32_t *)(address + APP_LOAD_ADDRESS);
}

//--------------------------------------------------------------------+
//
//--------------------------------------------------------------------+
void board_flash_init(void)
{

}

uint32_t board_flash_size(void)
{
  return 256;
}

void board_flash_read(uint32_t addr, void* buffer, uint32_t len)
{
  (void) addr;
  (void) buffer;
  (void) len;
}

void board_flash_flush(void)
{
}

void board_flash_write (uint32_t dst, void const *src, uint32_t len)
{
  (void) dst;
  (void) src;
  (void) len;
}

