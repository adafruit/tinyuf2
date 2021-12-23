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

// Debug helper, remove later
#define PRINTF(...)           ESP_LOGI("uf2", __VA_ARGS__)
#define PRINT_LOCATION()      ESP_LOGI("uf2", "%s: %d", __PRETTY_FUNCTION__, __LINE__)
#define PRINT_MESS(x)         ESP_LOGI("uf2", "%s", (char*)(x))
#define PRINT_STR(x)          ESP_LOGI("uf2", #x " = %s"   , (char*)(x) )
#define PRINT_INT(x)          ESP_LOGI("uf2", #x " = %d"  , (int32_t) (x) )
#define PRINT_HEX(x)          ESP_LOGI("uf2", #x " = 0x%X", (uint32_t) (x) )

#define PRINT_BUFFER(buf, n) \
  do {\
    uint8_t const* p8 = (uint8_t const*) (buf);\
    printf(#buf ": ");\
    for(uint32_t i=0; i<(n); i++) printf("%x ", p8[i]);\
    printf("\n");\
  }while(0)

#define FLASH_CACHE_SIZE          (64*1024)
#define FLASH_CACHE_INVALID_ADDR  0xffffffff

static uint32_t _fl_addr = FLASH_CACHE_INVALID_ADDR;
static uint8_t _fl_buf[FLASH_CACHE_SIZE] __attribute__((aligned(4)));

// uf2 will always write to ota0 partition
static esp_partition_t const * _part_ota0 = NULL;

void board_flash_init(void)
{
  _fl_addr = FLASH_CACHE_INVALID_ADDR;

  _part_ota0 = esp_partition_find_first(ESP_PARTITION_TYPE_APP, ESP_PARTITION_SUBTYPE_APP_OTA_0, NULL);
  assert(_part_ota0 != NULL);
}

uint32_t board_flash_size(void)
{
  return _part_ota0->size;
}

void board_flash_read(uint32_t addr, void* buffer, uint32_t len)
{
  esp_partition_read(_part_ota0, addr, buffer, len);
}

void board_flash_flush(void)
{
  if ( _fl_addr == FLASH_CACHE_INVALID_ADDR ) return;

  //PRINTF("Erase and Write at 0x%08X", _fl_addr);

  // Check if contents already matched
  bool content_matches = true;
  uint32_t const verify_sz = 4096;
  uint8_t* verify_buf = malloc(verify_sz);

  for(uint32_t count = 0; count < FLASH_CACHE_SIZE; count += verify_sz)
  {
    board_flash_read(_fl_addr + count, verify_buf, verify_sz);
    if ( 0 != memcmp(_fl_buf + count, verify_buf, verify_sz)  )
    {
      content_matches = false;
      break;
    }
  }
  free(verify_buf);

  // skip erase & write if content already matches
  if ( !content_matches )
  {
    esp_partition_erase_range(_part_ota0, _fl_addr, FLASH_CACHE_SIZE);
    esp_partition_write(_part_ota0, _fl_addr, _fl_buf, FLASH_CACHE_SIZE);
  }

  _fl_addr = FLASH_CACHE_INVALID_ADDR;
}

void board_flash_write (uint32_t addr, void const *data, uint32_t len)
{
  uint32_t new_addr = addr & ~(FLASH_CACHE_SIZE - 1);

  if ( new_addr != _fl_addr )
  {
    board_flash_flush();

    _fl_addr = new_addr;
    board_flash_read(new_addr, _fl_buf, FLASH_CACHE_SIZE);
  }

  memcpy(_fl_buf + (addr & (FLASH_CACHE_SIZE - 1)), data, len);
}


//--------------------------------------------------------------------+
// Self Update
//--------------------------------------------------------------------+

#ifdef TINYUF2_SELF_UPDATE

// boot2 binary converted by uf2conv.py
#include "boot2_bin.h"

static inline uint32_t uf2_min32(uint32_t x, uint32_t y)
{
  return (x < y) ? x : y;
}

// Erase and update boot stage2
static void update_boot2(const uint8_t * data, uint32_t datalen)
{
  // boot2 is always at 0x1000
  enum { BOOT2_ADDR = 0x1000 };

  // max size of boot2 is 28KB
  if ( datalen > 24*1024u ) return;

  esp_flash_t * flash_chip = esp_flash_default_chip;
  assert(flash_chip != NULL);

  //------------- Verify if content matches -------------//
  uint8_t* verify_buf = _fl_buf;
  bool content_matches = true;

  for(uint32_t count = 0; count < datalen; count += FLASH_CACHE_SIZE)
  {
    uint32_t const verify_len = uf2_min32(datalen - count, FLASH_CACHE_SIZE);
    esp_flash_read(flash_chip, verify_buf, BOOT2_ADDR + count, verify_len);

    if ( 0 != memcmp(data + count, verify_buf, verify_len) )
    {
      content_matches = false;
      break;
    }
  }

  PRINT_INT(content_matches);

  // nothing to do
  if (content_matches) return;

  //------------- Erase & Flash -------------//
  enum { SECTOR_SZ = 4096UL };

  // make len aligned to 4K (round div)
  uint32_t const erase_sz = (datalen + SECTOR_SZ - 1) / SECTOR_SZ;

  // erase
  esp_flash_erase_region(flash_chip, BOOT2_ADDR, erase_sz);

  // flash
  esp_flash_write(flash_chip, data, BOOT2_ADDR, datalen);
}

// Erase and write tinyuf2 partition
static void update_tinyuf2(const uint8_t * data, uint32_t datalen)
{
  esp_partition_t const * part_uf2 = esp_partition_find_first(ESP_PARTITION_TYPE_APP, ESP_PARTITION_SUBTYPE_APP_FACTORY, NULL);
  assert(part_uf2 != NULL);

  // Set UF2 as next boot regardless of flashing resule to prevent running this app again
  esp_ota_set_boot_partition(part_uf2);

  //------------- Verify if content matches -------------//
  uint8_t* verify_buf = _fl_buf;
  bool content_matches = true;

  for(uint32_t count = 0; count < datalen; count += FLASH_CACHE_SIZE)
  {
    uint32_t const verify_len = uf2_min32(datalen - count, FLASH_CACHE_SIZE);
    esp_partition_read(part_uf2, count, verify_buf, verify_len);

    if ( 0 != memcmp(data + count, verify_buf, verify_len) )
    {
      content_matches = false;
      break;
    }
  }

  // nothing to do
  if (!content_matches) return;

  //------------- Erase & Flash -------------//
  enum { SECTOR_SZ = 4096UL };

  // make len aligned to 4K (round div)
  uint32_t const erase_sz = (datalen + SECTOR_SZ - 1) / SECTOR_SZ;

  // Erase partition
  esp_partition_erase_range(part_uf2, 0, erase_sz);

  // Write new data
  esp_partition_write(part_uf2, 0, data, datalen);

  // Set UF2 as next boot
  esp_ota_set_boot_partition(part_uf2);
}

void board_self_update(const uint8_t * bootloader_bin, uint32_t bootloader_len)
{
  // Update TinyUF2 partition
  update_tinyuf2(bootloader_bin, bootloader_len);

  // Update boot2 stage partition
  update_boot2(binboot2, binboot2_len);

  // all done restart
  esp_restart();
}

#endif
