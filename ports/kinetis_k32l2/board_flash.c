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
#include "fsl_flash.h"
#include "tusb.h" // for logging

// FLASH
#define NO_CACHE        0xffffffff

#define FLASH_PAGE_SIZE 1024
#define FILESYSTEM_BLOCK_SIZE 256

static uint32_t bf_flash_page_addr = NO_CACHE;
static uint8_t  bf_flash_cache[FLASH_PAGE_SIZE] __attribute__((aligned(4)));
/*! @brief Flash driver Structure */
static flash_config_t bf_flash_config;
/*! @brief Flash cache driver Structure */
static ftfx_cache_config_t bf_cache_config;

//--------------------------------------------------------------------+
//
//--------------------------------------------------------------------+
void board_flash_init(void)
{
    uint32_t pflashBlockBase  = 0;
    uint32_t pflashTotalSize  = 0;
    uint32_t pflashSectorSize = 0;
    status_t result;   /* Return code from each flash driver function */
    /* Clean up Flash, Cache driver Structure*/
    memset(&bf_flash_config, 0, sizeof(flash_config_t));
    memset(&bf_cache_config, 0, sizeof(ftfx_cache_config_t));

    /* Setup flash driver structure for device and initialize variables. */
    result = FLASH_Init(&bf_flash_config);
    if (kStatus_FTFx_Success != result) {
        TU_LOG1("FLASH_Init failed");
    }
    /* Setup flash cache driver structure for device and initialize variables. */
    result = FTFx_CACHE_Init(&bf_cache_config);
    if (kStatus_FTFx_Success != result)
    {
        TU_LOG1("FTFx_CACHE_Init failed");
    }
    /* Get flash properties*/
    FLASH_GetProperty(&bf_flash_config, kFLASH_PropertyPflash0BlockBaseAddr, &pflashBlockBase);
    FLASH_GetProperty(&bf_flash_config, kFLASH_PropertyPflash0TotalSize, &pflashTotalSize);
    FLASH_GetProperty(&bf_flash_config, kFLASH_PropertyPflash0SectorSize, &pflashSectorSize);

    TU_LOG1("Base: 0x%08lX,  Total: 0x%08lX,  Sector: 0x%08lX\r\n",
            pflashBlockBase, pflashTotalSize, pflashSectorSize);
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
  status_t result;
//  uint32_t failedAddress, failedData;

  if ( bf_flash_page_addr == NO_CACHE ) return;

//  result = FLASH_VerifyProgram(&_flash_config, _flash_page_addr, FLASH_PAGE_SIZE, (const uint8_t *)_flash_cache, &failedAddress, &failedData);
//  if (result != kStatus_Success) {

  // skip matching contents
  if ( memcmp(bf_flash_cache, (void*) bf_flash_page_addr, FLASH_PAGE_SIZE) ) {
    TU_LOG1("Clear cache prefetch speculation for flush operation.\r\n");

    /* Pre-preparation work about flash Cache/Prefetch/Speculation. */
    FTFx_CACHE_ClearCachePrefetchSpeculation(&bf_cache_config, true);

    TU_LOG1("Erase and Write at address = 0x%08lX...\r\n", bf_flash_page_addr);
    __disable_irq();
    result = FLASH_Erase(&bf_flash_config, bf_flash_page_addr, FLASH_PAGE_SIZE, kFLASH_ApiEraseKey);
    if (kStatus_FTFx_Success != result) {
        TU_LOG1("FLASH_Erase failed at address = 0x%08lX\r\n",bf_flash_page_addr);
    }
    TU_LOG1("Erased...\r\n");
    result = FLASH_Program(&bf_flash_config, bf_flash_page_addr, bf_flash_cache, FLASH_PAGE_SIZE);
    if (kStatus_FTFx_Success != result) {
        TU_LOG1("FLASH_Program failed at address = 0x%08lX\r\n",bf_flash_page_addr);
    }
    __enable_irq();
    TU_LOG1("Programmed.\r\n");

    /* Post-preparation work about flash Cache/Prefetch/Speculation. */
    FTFx_CACHE_ClearCachePrefetchSpeculation(&bf_cache_config, false);
  }

  bf_flash_page_addr = NO_CACHE;
}


bool board_flash_write(uint32_t addr, void const* data, uint32_t len) {
  uint32_t newAddr = addr & ~(FLASH_PAGE_SIZE - 1);
  // int32_t result;

  if (newAddr != bf_flash_page_addr) {
    board_flash_flush();
    bf_flash_page_addr = newAddr;
    board_flash_read(newAddr, bf_flash_cache, FLASH_PAGE_SIZE);
    // result = FLASH_Read(&_flash_config, newAddr, _flash_cache, FLASH_PAGE_SIZE);
    // if (result != kStatus_Success) {
    //   TU_LOG1("Flash read error at address = 0x%08lX\r\n", _flash_page_addr);
    // }
  }
  memcpy(bf_flash_cache + (addr & (FLASH_PAGE_SIZE - 1)), data, len);

  return true;
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
