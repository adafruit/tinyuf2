#include "boards.h"

// From board_api.h

// HACK to execute our own functions, while using /src/main.c ....
//
// Option #1:
// * Always return `true` from `board_app_valid()`
// * Use board_app_jump() as the equivalent of `main()`
// * Note: will need to duplicate all the initialization code from `main()`...
// * Note: risk of breaking when `main()` changes
//
// Option #2:
// * define TINYUF2_DISPLAY as non-zero
// * Use `board_display_init()` as the equivalent of `main()`
// * Note: appears to also require other changes to compile
// * Note: risk of breaking when `main()` changes
// * Currently the option that most closely matches execution on real hardware
//
// Option #3:
// * Modify /src/main.c to support test-mode board
//
//
// Selected option #3.

//------------- Flash -------------//
uint32_t board_flash_size(void) { return CFG_UF2_FLASH_SIZE; }

uint32_t test_flash_write_count;
uint32_t test_flash_write_addr;
uint32_t test_flash_write_len;
uint32_t test_flash_flush_count;

// records the call only; never reads data, whose length the test may make out of range
bool board_flash_write(uint32_t addr, void const* data, uint32_t len) {
  (void) data;
  test_flash_write_count++;
  test_flash_write_addr = addr;
  test_flash_write_len = len;
  return true;
}

// not supported
void board_self_update(const uint8_t* bootloader_bin, uint32_t bootloader_len) {
  (void) bootloader_bin;
  (void) bootloader_len;
}

void board_flash_flush(void) {
  test_flash_flush_count++;
}

// not supported
bool board_flash_protect_bootloader(bool protect) {
  (void) protect;
  return false;
}

//------------- Interesting part of flash support for this test -------------//
void board_flash_read(uint32_t addr, void* buffer, uint32_t len) {
  if ((addr & 7) != 0) {
    // TODO - need to copy part of the first eight bytes
    exit(1); // failure exit
    addr += 8 - (addr & 7);
  }

  // EMBED address in each 32 bits of the FLASH
  uint32_t* dest = buffer;
  size_t incBytes = sizeof(*dest);
  uint32_t currentAddress = addr;

  while (len >= incBytes) {
    memcpy(dest, &currentAddress, incBytes); // unaligned memory possible

    len -= incBytes;
    dest++;
    currentAddress += incBytes;
  }
}
