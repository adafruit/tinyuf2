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
#include "boards.h"
#include "fsl_iap.h"
#include "fsl_iap_ffr.h"
#include "tusb.h" // for logging


// FLASH
#define NO_CACHE        0xffffffff

#define FLASH_PAGE_SIZE 512
#define FILESYSTEM_BLOCK_SIZE 256

static flash_config_t _flash_config;
static uint32_t _flash_page_addr = NO_CACHE;
static uint8_t  _flash_cache[FLASH_PAGE_SIZE] __attribute__((aligned(4)));

//--------------------------------------------------------------------+
//
//--------------------------------------------------------------------+
void board_flash_init(void)
{
  if (FLASH_Init(&_flash_config) == kStatus_Success) {
    TU_LOG2("Flash init successfull!!\r\n");
  } else {
    TU_LOG1("\r\n\r\n\t---- FLASH ERROR! ----\r\n");
  }
}

uint32_t board_flash_size(void)
{
  return BOARD_FLASH_SIZE;
}

void board_flash_read(uint32_t addr, void* buffer, uint32_t len)
{
  FLASH_Read(&_flash_config, addr, buffer, len);
}

void board_flash_flush(void)
{
  status_t status;
  uint32_t failedAddress, failedData;

  if ( _flash_page_addr == NO_CACHE ) return;

  status = FLASH_VerifyProgram(&_flash_config, _flash_page_addr, FLASH_PAGE_SIZE, (const uint8_t *)_flash_cache, &failedAddress, &failedData);

  if (status != kStatus_Success) {
    TU_LOG1("Erase and Write at address = 0x%08lX\r\n",_flash_page_addr);
    status = FLASH_Erase(&_flash_config, _flash_page_addr, FLASH_PAGE_SIZE, kFLASH_ApiEraseKey);
    status = FLASH_Program(&_flash_config, _flash_page_addr, _flash_cache, FLASH_PAGE_SIZE);
  }

  _flash_page_addr = NO_CACHE;
}

void board_flash_write (uint32_t addr, void const *data, uint32_t len)
{
  uint32_t newAddr = addr & ~(FLASH_PAGE_SIZE - 1);
  int32_t status;
    
  if (newAddr != _flash_page_addr) {
    board_flash_flush();
    _flash_page_addr = newAddr;
    status = FLASH_Read(&_flash_config, newAddr, _flash_cache, FLASH_PAGE_SIZE);
    if (status != kStatus_Success) {
      TU_LOG1("Flash read error at address = 0x%08lX\r\n", _flash_page_addr);
    }
  }
  memcpy(_flash_cache + (addr & (FLASH_PAGE_SIZE - 1)), data, len);
}

uint8_t board_usb_get_serial(uint8_t serial_id[16])
{
  FFR_GetUUID(&_flash_config, serial_id);
  return 16;
}

// Check if application is valid
bool board_app_valid(void) { 
  uint32_t resetVector[1];
  // 2nd word is App entry point (reset)
  FLASH_Read(&_flash_config, (BOARD_FLASH_APP_START +4), (uint8_t *)resetVector, 4);
  if ( (resetVector[0] >= BOARD_FLASH_APP_START) && (resetVector[0] < BOARD_FLASH_SIZE) ) {
    return true;
  } else {
    return false;
  }
}


#ifdef TINYUF2_SELF_UPDATE
void board_self_update(const uint8_t * bootloader_bin, uint32_t bootloader_len)
{
  (void) bootloader_bin;
  (void) bootloader_len;
}
#endif
