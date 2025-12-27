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
#include "romapi_flash.h"
#include "fsl_flexspi_nor_boot.h"

// compare and write tinyuf2 to flash every time it is running
#define COMPARE_AND_WRITE_TINYUF2 0

#define FLASH_CACHE_SIZE          4096
#define SECTOR_SIZE               (4 * 1024)
#define FLASH_CACHE_INVALID_ADDR  0xffffffff
#define FLASH_PAGE_SIZE 256

// on-board flash is connected to FLEXSPI2 on rt1064
#if defined(MIMXRT1064_SERIES)
  #define FLEXSPI_INSTANCE    1
  #define FLEXSPI_FLASH_BASE  FlexSPI2_AMBA_BASE
#elif defined(MIMXRT1176_cm7_SERIES)
  #define FLEXSPI_INSTANCE    1
  #define FLEXSPI_FLASH_BASE  FlexSPI1_AMBA_BASE
#else
  #define FLEXSPI_INSTANCE    0
  #define FLEXSPI_FLASH_BASE  FlexSPI_AMBA_BASE
#endif

// Mask off lower 12 bits to get FCFB offset
#define FLASH_FCFB_ADDR (FLEXSPI_FLASH_BASE + (((uint32_t)_fcfb_origin) & 0xFFFl))
#define FLASH_IVT_ADDR  (FLEXSPI_FLASH_BASE + 0x1000)

//--------------------------------------------------------------------+
//
//--------------------------------------------------------------------+

// Flash Configuration Structure
extern flexspi_nor_config_t const qspiflash_config;
static flexspi_nor_config_t       flash_cfg; // local copy since ROM API may modify it

#if defined(MIMXRT1176_cm7_SERIES)
  #define USE_BLHOST
extern const flexspi_nor_config_t qspiflash_config_copy;
extern const BOOT_DATA_T          g_boot_data_copy;
extern const ivt                  image_vector_table;
#endif

static uint32_t _flash_page_addr = FLASH_CACHE_INVALID_ADDR;
static uint8_t  _flash_cache[SECTOR_SIZE] __attribute__((aligned(4)));

//--------------------------------------------------------------------+
//
//--------------------------------------------------------------------+

// Write TinyUF2 from SRAM to Flash: fcfb + bootloader (ivt, interrupt, text)
static void write_tinyuf2_to_flash(void) {
  TUF2_LOG1("Writing TinyUF2 image to flash.\r\n");

#ifdef USE_BLHOST
  // blhost load-image with ivt at address 0, no FCFB in RAM, manual write it using copies
  // Write FCFB
  board_flash_write(FLASH_FCFB_ADDR, &qspiflash_config_copy, sizeof(flexspi_nor_config_t));

  // Write IVT (image vector table + boot data)
  board_flash_write(FLASH_IVT_ADDR, &image_vector_table, sizeof(ivt));
  board_flash_write(FLASH_IVT_ADDR + sizeof(ivt), &g_boot_data_copy, sizeof(BOOT_DATA_T));
  // DCD is not used, skip writing it

  // Write Interrupts + Text
  const uint8_t *image_data = (const uint8_t *)((uint32_t)_interrupts_origin);
  uint32_t       flash_addr = FLASH_IVT_ADDR + ((uint32_t)_ivt_length);
#else
  // sdphost write from fcfb to end of bootloader
  const uint8_t *image_data = (const uint8_t *)&qspiflash_config;
  uint32_t       flash_addr = FLASH_FCFB_ADDR;
#endif
  const uint32_t flash_end  = FLEXSPI_FLASH_BASE + BOARD_BOOT_LENGTH;

  while (flash_addr < flash_end) {
    board_flash_write(flash_addr, image_data, FLASH_PAGE_SIZE);
    flash_addr += FLASH_PAGE_SIZE;
    image_data += FLASH_PAGE_SIZE;
  }
  board_flash_flush();
  TUF2_LOG1("TinyUF2 copied to flash.\r\n");
}

void board_flash_init(void)
{
#if defined(MIMXRT1176_cm7_SERIES)
  // MIMXRT1176 requires ROM_API_Init to be called before using ROM API functions
  ROM_API_Init();
  flash_cfg = qspiflash_config_copy;
#else
  flash_cfg = qspiflash_config;
#endif

  ROM_FLEXSPI_NorFlash_Init(FLEXSPI_INSTANCE, &flash_cfg);

  // TinyUF2 will copy its image to flash if one of conditions meets:
  // - Boot Mode is '01' i.e Serial Download Mode (BootRom)
  // - Flash FCFB is invalid (blank)
  //
  // NOTE: Self-flash is only performed when running from RAM (loaded via SDP).
  // When running from flash (XIP mode), we skip self-flash since TinyUF2 is
  // already in flash and re-flashing while executing from flash would crash.
  const uint32_t boot_mode  = (SRC->SBMR2 & SRC_SBMR2_BMOD_MASK) >> SRC_SBMR2_BMOD_SHIFT;
  const bool     fcfb_valid = (*(uint32_t *)FLASH_FCFB_ADDR == FLEXSPI_CFG_BLK_TAG);

  TUF2_LOG1("Boot Mode = %lu, fcfb_valid = %u\r\n", boot_mode, fcfb_valid);
  if (boot_mode == 1 || !fcfb_valid) {
    write_tinyuf2_to_flash();
  }
}

uint32_t board_flash_size(void) {
  // TODO currently limit at 8MB since the CURRENT.UF2 can occupies all 32MB virtual disk
  uint32_t const max_size = 8*1024*1024;
  return (BOARD_FLASH_SIZE < max_size) ? BOARD_FLASH_SIZE : max_size;
}

void board_flash_read(uint32_t addr, void* buffer, uint32_t len)
{
  // Must write out anything in cache before trying to read.
  // board_flash_flush();

  memcpy(buffer, (uint8_t *)addr, len);
}

void board_flash_flush(void) {
  status_t status;

  if (_flash_page_addr == FLASH_CACHE_INVALID_ADDR) {
    return;
  }

  TUF2_LOG1("Erase and Write at address = 0x%08lX\r\n", _flash_page_addr);

  // Skip if data is the same
  if (memcmp(_flash_cache, (void *)_flash_page_addr, SECTOR_SIZE) != 0) {
    const uint32_t sector_addr = (_flash_page_addr - FLEXSPI_FLASH_BASE);

    __disable_irq();
    status = ROM_FLEXSPI_NorFlash_Erase(FLEXSPI_INSTANCE, &flash_cfg, sector_addr, SECTOR_SIZE);
    __enable_irq();

    // Use absolute address for cache invalidation, not the offset
    SCB_InvalidateDCache_by_Addr((uint32_t *)_flash_page_addr, SECTOR_SIZE);

    if ( status != kStatus_Success )
    {
      TUF2_LOG1("Erase failed: status = %ld!\r\n", status);
      return;
    }

    for ( int i = 0; i < SECTOR_SIZE / FLASH_PAGE_SIZE; ++i )
    {
      uint32_t const page_addr = sector_addr + i * FLASH_PAGE_SIZE;
      void* page_data =  _flash_cache + i * FLASH_PAGE_SIZE;

      __disable_irq();
      status = ROM_FLEXSPI_NorFlash_ProgramPage(FLEXSPI_INSTANCE, &flash_cfg, page_addr, (uint32_t *)page_data);
      __enable_irq();

      if ( status != kStatus_Success )
      {
        TUF2_LOG1("Page program failed: status = %ld!\r\n", status);
        return;
      }
    }

    // Use absolute address for cache invalidation, not the offset
    SCB_InvalidateDCache_by_Addr((uint32_t *)_flash_page_addr, SECTOR_SIZE);
  }

  _flash_page_addr = FLASH_CACHE_INVALID_ADDR;
}

bool board_flash_write(uint32_t addr, const void *src, uint32_t len) {
  const uint32_t page_addr = addr & ~(SECTOR_SIZE - 1);

  if (page_addr != _flash_page_addr) {
    // Write out anything in cache before overwriting it.
    board_flash_flush();

    _flash_page_addr = page_addr;

    // Copy the current contents of the entire page into the cache.
    memcpy(_flash_cache, (void*) page_addr, SECTOR_SIZE);
  }

  // Overwrite part or all of the page cache with the src data.
  memcpy(_flash_cache + (addr & (SECTOR_SIZE - 1)), src, len);

  return true;
}

void board_flash_erase_app(void)
{
  TUF2_LOG1("Erase whole chip\r\n");

  // Perform chip erase first
  ROM_FLEXSPI_NorFlash_Init(FLEXSPI_INSTANCE, &flash_cfg);
  ROM_FLEXSPI_NorFlash_EraseAll(FLEXSPI_INSTANCE, &flash_cfg);

  // Re-write bootloader to flash after chip erase (only when running from RAM)
  TUF2_LOG1("Erase app firmware: ");
  write_tinyuf2_to_flash();
}

bool board_flash_protect_bootloader(bool protect)
{
  // TODO implement later
  (void) protect;
  return false;
}
