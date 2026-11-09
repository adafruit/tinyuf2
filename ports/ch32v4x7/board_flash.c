// SPDX-FileCopyrightText: Copyright (c) 2026 Adafruit Industries
// SPDX-License-Identifier: MIT
#include "board_api.h"

// WCH erases 4 KB but programs 256 bytes. Preserve neighboring UF2 blocks,
// including when the host sends duplicate blocks or changes page order.
static uint32_t page[BOARD_FLASH_PAGE_SIZE / 4];
static uint32_t first_page[BOARD_FLASH_PAGE_SIZE / 4];
static uint32_t page_address;
static bool     page_dirty;
static bool     updating;
static bool     failed;

static bool write_page(uint32_t address, uint32_t *data) {
  __disable_irq();
  FLASH_Status status = FLASH_ROM_ERASE(FLASH_BASE + address, BOARD_FLASH_PAGE_SIZE);
  if (status == FLASH_COMPLETE) {
    if (address == BOARD_FLASH_APP_START) {
      // Commit the reset vector only after the rest of the first sector.
      status = FLASH_ROM_WRITE(FLASH_BASE + address + 256, data + 64, BOARD_FLASH_PAGE_SIZE - 256);
      if (status == FLASH_COMPLETE) {
        status = FLASH_ROM_WRITE(FLASH_BASE + address, data, 256);
      }
    } else {
      status = FLASH_ROM_WRITE(FLASH_BASE + address, data, BOARD_FLASH_PAGE_SIZE);
    }
  }
  __asm volatile("fence.i" ::: "memory");
  __enable_irq();
  if (status != FLASH_COMPLETE || memcmp((void *)(FLASH_BASE + address), data, BOARD_FLASH_PAGE_SIZE)) {
    failed = true;
    return false;
  }
  return true;
}

static bool flush_page(void) {
  if (page_dirty) {
    if (!write_page(page_address, page)) {
      return false;
    }
    page_dirty = false;
  }
  return !failed;
}

void board_flash_init(void) {
  page_dirty = updating = failed = false;
}

uint32_t board_flash_size(void) {
  return BOARD_FLASH_SIZE - BOARD_FLASH_APP_START;
}

void board_flash_read(uint32_t addr, void *buffer, uint32_t len) {
  memcpy(buffer, (const void *)(FLASH_BASE + addr), len);
}

bool board_flash_write(uint32_t addr, const void *data, uint32_t len) {
  // UF2 addresses are zero-based, as in the linked RISC-V application.
  // Reject aliases, bootloader writes, crossing the end and partial pages.
  if (failed || len != 256 || (addr & 255u) || addr < BOARD_FLASH_APP_START || addr > BOARD_FLASH_SIZE - len) {
    return false;
  }
  if (!updating) {
    memcpy(first_page, (const void *)(FLASH_BASE + BOARD_FLASH_APP_START), sizeof first_page);
    __disable_irq();
    FLASH_Status status = FLASH_ROM_ERASE(FLASH_BASE + BOARD_FLASH_APP_START, BOARD_FLASH_PAGE_SIZE);
    __asm volatile("fence.i" ::: "memory");
    __enable_irq();
    if (status != FLASH_COMPLETE) {
      failed = true;
      return false;
    }
    updating = true;
  }
  const uint32_t base = addr & ~(BOARD_FLASH_PAGE_SIZE - 1u);
  if (base == BOARD_FLASH_APP_START) {
    memcpy((uint8_t *)first_page + (addr - base), data, len);
    return true;
  }
  if (!page_dirty || base != page_address) {
    if (!flush_page()) {
      return false;
    }
    page_address = base;
    memcpy(page, (const void *)(FLASH_BASE + base), sizeof page);
  }
  memcpy((uint8_t *)page + (addr - base), data, len);
  page_dirty = true;
  return true;
}

void board_flash_flush(void) {
  if (updating && flush_page() && write_page(BOARD_FLASH_APP_START, first_page)) {
    updating = false;
  }
}

bool board_flash_ok(void) {
  return !failed && !updating;
}

void board_flash_erase_app(void) {
  __disable_irq();
  FLASH_Status status = FLASH_ROM_ERASE(FLASH_BASE + BOARD_FLASH_APP_START, BOARD_FLASH_SIZE - BOARD_FLASH_APP_START);
  __asm volatile("fence.i" ::: "memory");
  __enable_irq();
  failed = status != FLASH_COMPLETE;
}

bool board_flash_protect_bootloader(bool protect) {
  // Bounds are enforced above. Do not change the user's option bytes.
  (void)protect;
  return false;
}
