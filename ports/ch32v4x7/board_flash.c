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

/** Erase and verify code flash with interrupts disabled by the caller.
 * The SDK can report FLASH_COMPLETE even for write-protected sectors.
 */
static bool erase_region(uint32_t address, uint32_t length) {
  FLASH_Status status = FLASH_ROM_ERASE(FLASH_BASE + address, length);
  __asm volatile("fence.i" ::: "memory");
  if (status != FLASH_COMPLETE) {
    failed = true;
    return false;
  }
  const volatile uint32_t *words = (const volatile uint32_t *)(FLASH_BASE + address);
  for (uint32_t i = 0; i < length / sizeof(*words); i++) {
    // WCH's erased code-flash value is not the usual all-ones word.
    if (words[i] != 0xe339e339u) {
      failed = true;
      return false;
    }
  }
  return true;
}

/** Program and verify one sector, committing the reset-vector block last. */
static bool write_page(uint32_t address, uint32_t *data) {
  __disable_irq();
  bool ok = erase_region(address, BOARD_FLASH_PAGE_SIZE);
  if (ok && address == BOARD_FLASH_APP_START) {
    FLASH_Status status = FLASH_ROM_WRITE(FLASH_BASE + address + 256, data + 64, BOARD_FLASH_PAGE_SIZE - 256);
    __asm volatile("fence.i" ::: "memory");
    // Do not install a reset vector until the rest of the sector reads back.
    ok = status == FLASH_COMPLETE &&
         memcmp((const void *)(FLASH_BASE + address + 256), data + 64, BOARD_FLASH_PAGE_SIZE - 256) == 0;
    if (ok) {
      status = FLASH_ROM_WRITE(FLASH_BASE + address, data, 256);
      __asm volatile("fence.i" ::: "memory");
      ok = status == FLASH_COMPLETE && memcmp((const void *)(FLASH_BASE + address), data, BOARD_FLASH_PAGE_SIZE) == 0;
    }
  } else if (ok) {
    FLASH_Status status = FLASH_ROM_WRITE(FLASH_BASE + address, data, BOARD_FLASH_PAGE_SIZE);
    __asm volatile("fence.i" ::: "memory");
    ok = status == FLASH_COMPLETE && memcmp((const void *)(FLASH_BASE + address), data, BOARD_FLASH_PAGE_SIZE) == 0;
  }
  if (!ok) {
    if (address == BOARD_FLASH_APP_START) {
      // A failed first-block readback may still contain a valid jump instruction.
      // Remove it so a later reset cannot start the damaged application.
      erase_region(address, BOARD_FLASH_PAGE_SIZE);
    }
    failed = true;
  }
  __enable_irq();
  return ok;
}

/** Commit a dirty non-vector sector and retain any programming failure. */
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
  // check_dfu_mode() may already have attempted an application erase.
  // Preserve its error; a reset starts a new session with zero-initialized state.
  page_dirty = updating = false;
}

uint32_t board_flash_size(void) {
  return BOARD_FLASH_SIZE - BOARD_FLASH_APP_START;
}

void board_flash_read(uint32_t addr, void *buffer, uint32_t len) {
  memcpy(buffer, (const void *)(FLASH_BASE + addr), len);
}

/** Buffer a UF2 payload after invalidating and verifying the old reset sector. */
bool board_flash_write(uint32_t addr, const void *data, uint32_t len) {
  // UF2 addresses are zero-based, as in the linked RISC-V application.
  // Reject aliases, bootloader writes, crossing the end and partial pages.
  if (failed || len != 256 || (addr & 255u) || addr < BOARD_FLASH_APP_START || addr > BOARD_FLASH_SIZE - len) {
    return false;
  }
  if (!updating) {
    memcpy(first_page, (const void *)(FLASH_BASE + BOARD_FLASH_APP_START), sizeof first_page);
    __disable_irq();
    bool erased = erase_region(BOARD_FLASH_APP_START, BOARD_FLASH_PAGE_SIZE);
    __enable_irq();
    if (!erased) {
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

/** Commit remaining data and the saved vector sector only for a healthy update. */
void board_flash_flush(void) {
  if (!failed && updating && flush_page() && write_page(BOARD_FLASH_APP_START, first_page)) {
    updating = false;
  }
}

/** Report whether all accepted data reached flash without a latched error. */
bool board_flash_ok(void) {
  return !failed && !updating;
}

/** Erase and verify the whole application without altering protection options. */
void board_flash_erase_app(void) {
  __disable_irq();
  // Invalidate the reset sector first. If it is protected, leave the rest of
  // the old application intact instead of creating a bootable partial erase.
  if (erase_region(BOARD_FLASH_APP_START, BOARD_FLASH_PAGE_SIZE)) {
    erase_region(BOARD_FLASH_APP_START + BOARD_FLASH_PAGE_SIZE,
                 BOARD_FLASH_SIZE - BOARD_FLASH_APP_START - BOARD_FLASH_PAGE_SIZE);
  }
  __enable_irq();
}

bool board_flash_protect_bootloader(bool protect) {
  // Bounds are enforced above. Do not change the user's option bytes.
  (void)protect;
  return false;
}
