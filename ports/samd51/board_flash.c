#include "board_api.h"

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM
//--------------------------------------------------------------------+

// SAMD51 erases 8 KB blocks and programs quad words (16 bytes). UF2 payloads are 256 bytes
#define FLASH_BLOCK_SIZE NVMCTRL_BLOCK_SIZE
#define FLASH_ROW_SIZE   256
#define QUAD_WORD_SIZE   16

#define USER_PAGE_ADDR   0x00804000
#define USER_PAGE_SIZE   512
#define BOOTPROT_POS     26
#define BOOTPROT_MSK     (0xFu << BOOTPROT_POS)

enum {
  BLOCK_COUNT    = BOARD_FLASH_SIZE / FLASH_BLOCK_SIZE,
  ROWS_PER_BLOCK = FLASH_BLOCK_SIZE / FLASH_ROW_SIZE
};
_Static_assert(ROWS_PER_BLOCK <= 32, "good_rows is a 32 bit mask");

// rows of each block known to hold their data, written or found identical since the flash was initialized.
// They are written back when the block has to be erased.
static uint32_t good_rows[BLOCK_COUNT];
// holds the rows to keep while their block is erased, or a block image while updating the bootloader
static uint8_t block_cache[FLASH_BLOCK_SIZE];

//--------------------------------------------------------------------+
// Internal Helper
//--------------------------------------------------------------------+
static inline void wait_ready(void) {
  while (NVMCTRL->STATUS.bit.READY == 0) {}
}

static inline void exec_cmd(uint32_t cmd) {
  wait_ready();
  NVMCTRL->CTRLB.reg = NVMCTRL_CTRLB_CMDEX_KEY | cmd;
  wait_ready();
}

// The cache in Rev A is not reliable when reading and writing to the NVM
static void cache_disable(void) {
  NVMCTRL->CTRLA.bit.CACHEDIS0 = true;
  NVMCTRL->CTRLA.bit.CACHEDIS1 = true;
}

// Flash starts at address 0: volatile keeps reads of the bootloader from being treated as null dereferences
static bool is_blank(uint32_t addr, uint32_t size) {
  const volatile uint32_t *flash = (const volatile uint32_t *)addr;
  for (uint32_t i = 0; i < size / sizeof(uint32_t); i++) {
    if (flash[i] != 0xffffffff) {
      return false;
    }
  }
  return true;
}

static bool is_equal(uint32_t addr, const uint8_t *data, uint32_t size) {
  const volatile uint8_t *flash = (const volatile uint8_t *)addr;
  for (uint32_t i = 0; i < size; i++) {
    if (flash[i] != data[i]) {
      return false;
    }
  }
  return true;
}

static bool is_valid_row(uint32_t addr, uint32_t len) {
  return len == FLASH_ROW_SIZE && (addr % FLASH_ROW_SIZE) == 0 && addr >= BOARD_FLASH_APP_START &&
         addr <= BOARD_FLASH_ADDR_ZERO + BOARD_FLASH_SIZE - len;
}

// Erase a block, skipped if it is already blank
static bool flash_erase(uint32_t block) {
  TUF2_ASSERT(block < BLOCK_COUNT);

  const uint32_t addr = BOARD_FLASH_ADDR_ZERO + block * FLASH_BLOCK_SIZE;
  if (is_blank(addr, FLASH_BLOCK_SIZE)) {
    return true;
  }

  TUF2_LOG1("Erase: %08lX size = %u KB ... ", addr, FLASH_BLOCK_SIZE / 1024);
  cache_disable();
  NVMCTRL->ADDR.reg = addr;
  exec_cmd(NVMCTRL_CTRLB_CMD_EB);
  TUF2_ASSERT(is_blank(addr, FLASH_BLOCK_SIZE));
  TUF2_LOG1("OK\r\n");

  return true;
}

// Quad word writes allow 256 byte UF2 payloads: a 512 byte page write would need the
// neighbouring payload read back from flash
static bool flash_program(uint32_t dst, const uint8_t *src, uint32_t len) {
  TUF2_LOG1("Write flash at address %08lX\r\n", dst);

  cache_disable();
  NVMCTRL->CTRLA.bit.WMODE = NVMCTRL_CTRLA_WMODE_MAN_Val;
  exec_cmd(NVMCTRL_CTRLB_CMD_PBC);

  for (uint32_t i = 0; i < len; i += QUAD_WORD_SIZE) {
    const uint32_t     chunk = (len - i) < QUAD_WORD_SIZE ? (len - i) : QUAD_WORD_SIZE;
    volatile uint32_t *flash = (volatile uint32_t *)(dst + i);

    uint32_t words[QUAD_WORD_SIZE / sizeof(uint32_t)];
    memset(words, 0xff, sizeof(words));
    memcpy(words, src + i, chunk);

    // writes to the page buffer must be 16 or 32 bits wide
    wait_ready();
    for (uint32_t w = 0; w < QUAD_WORD_SIZE / sizeof(uint32_t); w++) {
      flash[w] = words[w];
    }

    NVMCTRL->ADDR.reg = dst + i;
    exec_cmd(NVMCTRL_CTRLB_CMD_WQW);
  }

  TUF2_VERIFY(is_equal(dst, src, len));
  return true;
}

// Erase a block, writing back the rows to keep
static bool flash_erase_block_keep_rows(uint32_t block, uint32_t keep) {
  const uint32_t base = BOARD_FLASH_ADDR_ZERO + block * FLASH_BLOCK_SIZE;

  for (uint32_t row = 0; row < ROWS_PER_BLOCK; row++) {
    if (keep & (1u << row)) {
      memcpy(block_cache + row * FLASH_ROW_SIZE, (const void *)(base + row * FLASH_ROW_SIZE), FLASH_ROW_SIZE);
    }
  }

  TUF2_VERIFY(flash_erase(block));

  for (uint32_t row = 0; row < ROWS_PER_BLOCK; row++) {
    if (keep & (1u << row)) {
      TUF2_VERIFY(flash_program(base + row * FLASH_ROW_SIZE, block_cache + row * FLASH_ROW_SIZE, FLASH_ROW_SIZE));
    }
  }

  return true;
}

// BOOTPROT protects the first 15 - BOOTPROT blocks of 8 KB, it is loaded from the user page at reset
static uint32_t bootprot_value(void) {
  return 15 - BOARD_FLASH_APP_START / FLASH_BLOCK_SIZE;
}

//--------------------------------------------------------------------+
// Board API
//--------------------------------------------------------------------+
void board_flash_init(void) {
  memset(good_rows, 0, sizeof(good_rows));
}

uint32_t board_flash_size(void) {
  return BOARD_FLASH_SIZE;
}

void board_flash_read(uint32_t addr, void *buffer, uint32_t len) {
  memcpy(buffer, (void *)addr, len);
}

void board_flash_flush(void) {
}

bool board_flash_write(uint32_t addr, const void *data, uint32_t len) {
  // a UF2 file may target anything: only accept whole rows of the application area
  TUF2_VERIFY(is_valid_row(addr, len));

  const uint32_t block   = addr / FLASH_BLOCK_SIZE;
  const uint32_t row_bit = 1u << ((addr % FLASH_BLOCK_SIZE) / FLASH_ROW_SIZE);

  // a row already holding its data is left alone
  if (is_equal(addr, data, len)) {
    good_rows[block] |= row_bit;
    return true;
  }

  // flash can only be programmed where it is blank: otherwise the block is erased, keeping the good rows
  if (!is_blank(addr, len)) {
    TUF2_VERIFY(flash_erase_block_keep_rows(block, good_rows[block] & ~row_bit));
  }

  TUF2_VERIFY(flash_program(addr, data, len));
  good_rows[block] |= row_bit;
  return true;
}

void board_flash_erase_app(void) {
  // erasing the first block of the app is enough to invalidate it
  flash_erase(BOARD_FLASH_APP_START / FLASH_BLOCK_SIZE);
}

bool board_flash_protect_bootloader(bool protect) {
  if (!protect) {
    // lift the protection until the next reset
    exec_cmd(NVMCTRL_CTRLB_CMD_SBPDIS);
    return true;
  }

  volatile uint32_t *const user_page = (volatile uint32_t *)USER_PAGE_ADDR;
  // an erased user page holds no valid fuses: leave it alone
  TUF2_VERIFY(user_page[0] != 0xffffffff);

  const uint32_t bootprot = bootprot_value();
  const uint32_t current  = (user_page[0] & BOOTPROT_MSK) >> BOOTPROT_POS;
  TUF2_LOG1("Protection: current = %lu, request = %lu\r\n", current, bootprot);

  if (current == bootprot) {
    return true;
  }

  uint32_t fuses[USER_PAGE_SIZE / sizeof(uint32_t)];
  memcpy(fuses, (const void *)USER_PAGE_ADDR, sizeof(fuses));
  fuses[0] = (fuses[0] & ~BOOTPROT_MSK) | (bootprot << BOOTPROT_POS);

  cache_disable();
  NVMCTRL->CTRLA.bit.WMODE = NVMCTRL_CTRLA_WMODE_MAN_Val;
  NVMCTRL->ADDR.reg        = USER_PAGE_ADDR;
  exec_cmd(NVMCTRL_CTRLB_CMD_EP);
  exec_cmd(NVMCTRL_CTRLB_CMD_PBC);
  for (uint32_t i = 0; i < sizeof(fuses) / sizeof(uint32_t); i += QUAD_WORD_SIZE / sizeof(uint32_t)) {
    for (uint32_t w = 0; w < QUAD_WORD_SIZE / sizeof(uint32_t); w++) {
      user_page[i + w] = fuses[i + w];
    }
    NVMCTRL->ADDR.reg = (uint32_t)&user_page[i];
    exec_cmd(NVMCTRL_CTRLB_CMD_WQW);
  }

  // the new value is only loaded at reset, and must not be retried if the write failed
  TUF2_VERIFY(((user_page[0] & BOOTPROT_MSK) >> BOOTPROT_POS) == bootprot);
  NVIC_SystemReset();
  return true;
}

#ifdef TINYUF2_SELF_UPDATE

static bool is_new_bootloader_valid(const uint8_t *bootloader_bin, uint32_t bootloader_len) {
  // at least larger than vector table, and must leave the application untouched
  if (bootloader_len < 1024 || bootloader_len > BOARD_FLASH_APP_START) {
    return false;
  }

  const uint32_t *vector = (const uint32_t *)(uintptr_t)bootloader_bin;
  const uint32_t  sp     = vector[0];
  const uint32_t  entry  = vector[1];

  // 1st word is stack pointer (must be in SRAM region)
  if ((sp & 0xff000003) != 0x20000000) {
    return false;
  }

  // 2nd word is the reset handler, must be inside the bootloader and have the Thumb bit set
  if (entry >= BOARD_FLASH_APP_START || (entry & 1u) == 0) {
    return false;
  }

  return true;
}

// Make a block of the bootloader area hold its part of the new bootloader and nothing else
static bool bootloader_block_update(uint32_t block, const uint8_t *bootloader_bin, uint32_t bootloader_len) {
  const uint32_t base   = BOARD_FLASH_ADDR_ZERO + block * FLASH_BLOCK_SIZE;
  const uint32_t offset = block * FLASH_BLOCK_SIZE;
  uint32_t       size   = 0;
  if (offset < bootloader_len) {
    size = ((bootloader_len - offset) < FLASH_BLOCK_SIZE) ? (bootloader_len - offset) : FLASH_BLOCK_SIZE;
  }

  memset(block_cache, 0xff, sizeof(block_cache));
  memcpy(block_cache, bootloader_bin + offset, size);
  if (is_equal(base, block_cache, FLASH_BLOCK_SIZE)) {
    return true;
  }

  TUF2_VERIFY(flash_erase(block));
  return flash_program(base, block_cache, size);
}

// Runs from RAM, it erases the block holding the code that called it. Rewriting programmed flash with zeros
// instead would leave the quad word with an inconsistent ECC.
static __attribute__((section(".ramfunc"), noinline, noreturn)) void flash_erase_block_and_reset(uint32_t addr) {
  __disable_irq();
  NVMCTRL->ADDR.reg  = addr;
  NVMCTRL->CTRLB.reg = NVMCTRL_CTRLB_CMDEX_KEY | NVMCTRL_CTRLB_CMD_EB;
  while (NVMCTRL->STATUS.bit.READY == 0) {}

  SCB->AIRCR = (0x5FAu << SCB_AIRCR_VECTKEY_Pos) | SCB_AIRCR_SYSRESETREQ_Msk;
  __DSB();
  while (1) {}
}

void board_self_update(const uint8_t *bootloader_bin, uint32_t bootloader_len) {
  // On failure this application stays in place so the update can be tried again
  if (!is_new_bootloader_valid(bootloader_bin, bootloader_len)) {
    TUF2_LOG1("Invalid bootloader image\r\n");
    return;
  }

  // Note: Don't protect bootloader when done, leave that to the new bootloader
  // since it may or may not enable protection.
  board_flash_protect_bootloader(false);

  // keep writing until flash contents matches the new bootloader data, the rest of the bootloader area blank
  bool updated = false;
  for (uint32_t retry = 0; retry < 3 && !updated; retry++) {
    updated = true;
    for (uint32_t block = 0; block < BOARD_FLASH_APP_START / FLASH_BLOCK_SIZE && updated; block++) {
      updated = bootloader_block_update(block, bootloader_bin, bootloader_len);
    }
  }

  if (!updated) {
    TUF2_LOG1("Bootloader update failed\r\n");
    return;
  }

  // self-destruct: erase the first block of this application so the bootloader does not run it again
  flash_erase_block_and_reset(BOARD_FLASH_APP_START);
}
#endif
