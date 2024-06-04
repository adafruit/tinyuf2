/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2020 Ha Thach for Adafruit Industries
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

#include <string.h>
#include "esp_log.h"
#include "esp_system.h"
#include "esp_partition.h"
#include "esp_ota_ops.h"

#include "spi_flash_chip_driver.h"
#include "board_api.h"

#define FLASH_CACHE_SIZE          (64*1024)
#define FLASH_CACHE_INVALID_ADDR  0xffffffff

static uint32_t _fl_addr = FLASH_CACHE_INVALID_ADDR;
static uint8_t _fl_buf[FLASH_CACHE_SIZE] __attribute__((aligned(4)));

// uf2 will always write to ota0 partition
static esp_partition_t const* _part_ota0 = NULL;

void board_flash_init(void) {
  _fl_addr = FLASH_CACHE_INVALID_ADDR;

  _part_ota0 = esp_partition_find_first(ESP_PARTITION_TYPE_APP, ESP_PARTITION_SUBTYPE_APP_OTA_0, NULL);
  assert(_part_ota0 != NULL);
}

uint32_t board_flash_size(void) {
  return _part_ota0->size;
}

void board_flash_read(uint32_t addr, void* buffer, uint32_t len) {
  esp_partition_read(_part_ota0, addr, buffer, len);
}

void board_flash_flush(void) {
  if (_fl_addr == FLASH_CACHE_INVALID_ADDR) return;

  TUF2_LOG1("Erase and Write at 0x%08lX", _fl_addr);

  // Check if contents already matched
  bool content_matches = true;
  uint32_t const verify_sz = 4096;
  uint8_t* verify_buf = malloc(verify_sz);

  for (uint32_t count = 0; count < FLASH_CACHE_SIZE; count += verify_sz) {
    board_flash_read(_fl_addr + count, verify_buf, verify_sz);
    if (0 != memcmp(_fl_buf + count, verify_buf, verify_sz)) {
      content_matches = false;
      break;
    }
  }
  free(verify_buf);

  // skip erase & write if content already matches
  if (!content_matches) {
    esp_partition_erase_range(_part_ota0, _fl_addr, FLASH_CACHE_SIZE);
    esp_partition_write(_part_ota0, _fl_addr, _fl_buf, FLASH_CACHE_SIZE);
  }

  _fl_addr = FLASH_CACHE_INVALID_ADDR;
}

bool board_flash_write(uint32_t addr, void const* data, uint32_t len) {
  uint32_t new_addr = addr & ~(FLASH_CACHE_SIZE - 1);

  if (new_addr != _fl_addr) {
    board_flash_flush();

    _fl_addr = new_addr;
    board_flash_read(new_addr, _fl_buf, FLASH_CACHE_SIZE);
  }

  memcpy(_fl_buf + (addr & (FLASH_CACHE_SIZE - 1)), data, len);

  return true;
}

bool board_flash_protect_bootloader(bool protect) {
  // TODO implement later
  (void) protect;
  return false;
}


//--------------------------------------------------------------------+
// Self Update
//--------------------------------------------------------------------+

#ifdef TINYUF2_SELF_UPDATE
void board_self_update(const uint8_t * bootloader_bin, uint32_t bootloader_len) {
  enum { SECTOR_SZ = 4096UL };
  esp_partition_t const * _part_uf2;

  _part_uf2 = esp_partition_find_first(ESP_PARTITION_TYPE_APP, ESP_PARTITION_SUBTYPE_APP_FACTORY, NULL);
  assert(_part_uf2 != NULL);

  // make len aligned to 4K
  uint32_t erase_sz = (bootloader_len & ~(SECTOR_SZ-1));
  if (bootloader_len & (SECTOR_SZ-1)) erase_sz += SECTOR_SZ;

  // Erase old bootloader
  esp_partition_erase_range(_part_uf2, 0, erase_sz);

  // Write new bootloader
  esp_partition_write(_part_uf2, 0, bootloader_bin, bootloader_len);

  // Set UF2 as next boot and restart
  esp_ota_set_boot_partition(_part_uf2);
  esp_restart();
}
#endif
