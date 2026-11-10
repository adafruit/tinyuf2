// SPDX-License-Identifier: MIT
// Fault-injection model of the CH32 flash API; this does not emulate its timing.
#ifdef NDEBUG
  #undef NDEBUG
#endif
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

// Supply only the board API's hardware dependencies to the real implementation.
#define BOARDS_H
#define BOARD_FLASH_SIZE      (512u * 1024u)
#define BOARD_FLASH_APP_START 0x8000u
#define BOARD_FLASH_PAGE_SIZE 4096u
static uint32_t flash_words[BOARD_FLASH_SIZE / 4];
#define FLASH_BASE ((uintptr_t)flash_words)
typedef enum {
  FLASH_COMPLETE,
  FLASH_ERROR
} FLASH_Status;
static uint32_t protected_word, corrupt_word;
static unsigned program_calls, vector_programs;
static bool     program_error;

static void __disable_irq(void) {
}
static void __enable_irq(void) {
}

/** Emulate an erase that silently leaves a protected word unchanged. */
static FLASH_Status FLASH_ROM_ERASE(uintptr_t address, uint32_t length) {
  uint32_t offset = address - FLASH_BASE;
  assert(offset >= BOARD_FLASH_APP_START && offset + length <= BOARD_FLASH_SIZE);
  for (uint32_t i = offset; i < offset + length; i += 4) {
    if (i != protected_word) {
      flash_words[i / 4] = 0xe339e339u;
    }
  }
  return FLASH_COMPLETE;
}

/** Program bytes, optionally returning an error or corrupting readback. */
static FLASH_Status FLASH_ROM_WRITE(uintptr_t address, uint32_t *data, uint32_t length) {
  uint32_t offset = address - FLASH_BASE;
  assert(offset >= BOARD_FLASH_APP_START && offset + length <= BOARD_FLASH_SIZE);
  program_calls++;
  vector_programs += offset == BOARD_FLASH_APP_START;
  memcpy((void *)address, data, length);
  if (corrupt_word >= offset && corrupt_word < offset + length) {
    flash_words[corrupt_word / 4] ^= 0x01000000u;
  }
  return program_error ? FLASH_ERROR : FLASH_COMPLETE;
}

// Ignore only the RISC-V instruction-cache fence in the native model.
// The function-like volatile macro leaves ordinary volatile qualifiers intact.
#define __asm
#define volatile(...) \
  do {                \
  } while (0)
#ifndef FLASH_SOURCE
  #define FLASH_SOURCE "../ch32v4x7/board_flash.c"
#endif
#include FLASH_SOURCE
#undef volatile
#undef __asm

static uint32_t payload[64];

/** Start a power-on state with an existing application and recognizable data. */
static void reset_flash(void) {
  memset(flash_words, 0x55, sizeof(flash_words));
  memset(payload, 0xa5, sizeof(payload));
  payload[0]     = 0x0000006f; // An otherwise bootable RISC-V jump.
  protected_word = corrupt_word = UINT32_MAX;
  program_calls = vector_programs = 0;
  program_error = failed = false;
  board_flash_init();
}

/** Verify that all modeled operations preserve the bootloader region. */
static void check_bootloader(void) {
  for (unsigned i = 0; i < BOARD_FLASH_APP_START / 4; i++) {
    assert(flash_words[i] == 0x55555555u);
  }
}

/** Buffer a reset-vector block without installing it yet. */
static void begin_update(void) {
  bool accepted = board_flash_write(BOARD_FLASH_APP_START, payload, sizeof(payload));
  assert(accepted);
  assert(flash_words[BOARD_FLASH_APP_START / 4] == 0xe339e339u);
  assert(!board_flash_ok());
}

/** Exercise successful buffering and each erase/program failure boundary. */
int main(void) {
  reset_flash();
  // Shuffled and duplicate blocks still preserve neighboring payloads.
  bool accepted = board_flash_write(BOARD_FLASH_APP_START + 4096, payload, sizeof(payload));
  assert(accepted);
  begin_update();
  accepted = board_flash_write(BOARD_FLASH_APP_START, payload, sizeof(payload));
  assert(accepted);
  board_flash_flush();
  assert(board_flash_ok() && vector_programs == 1);
  assert(memcmp(&flash_words[BOARD_FLASH_APP_START / 4], payload, sizeof(payload)) == 0);
  assert(memcmp(&flash_words[(BOARD_FLASH_APP_START + 4096) / 4], payload, sizeof(payload)) == 0);
  assert(flash_words[(BOARD_FLASH_APP_START + 256) / 4] == 0x55555555u);
  check_bootloader();

  for (unsigned offset = 0; offset <= 256; offset += 256) {
    reset_flash();
    protected_word = BOARD_FLASH_APP_START + offset;
    accepted       = board_flash_write(BOARD_FLASH_APP_START + 4096, payload, sizeof(payload));
    assert(!accepted && failed && program_calls == 0);
    assert(flash_words[(BOARD_FLASH_APP_START + 4096) / 4] == 0x55555555u);
    check_bootloader();
  }

  reset_flash();
  begin_update();
  corrupt_word = BOARD_FLASH_APP_START + 256;
  board_flash_flush();
  assert(!board_flash_ok() && vector_programs == 0);
  assert(flash_words[BOARD_FLASH_APP_START / 4] == 0xe339e339u);
  unsigned calls = program_calls;
  board_flash_flush();
  assert(program_calls == calls);
  check_bootloader();

  reset_flash();
  begin_update();
  corrupt_word = BOARD_FLASH_APP_START + 12; // Reset instruction itself still matches.
  board_flash_flush();
  assert(!board_flash_ok() && vector_programs == 1);
  assert(flash_words[BOARD_FLASH_APP_START / 4] == 0xe339e339u);
  check_bootloader();

  reset_flash();
  begin_update();
  accepted = board_flash_write(BOARD_FLASH_APP_START + 4096, payload, sizeof(payload));
  assert(accepted);
  program_error = true;
  board_flash_flush();
  assert(!board_flash_ok() && vector_programs == 0);
  assert(flash_words[BOARD_FLASH_APP_START / 4] == 0xe339e339u);
  check_bootloader();

  reset_flash();
  protected_word = BOARD_FLASH_APP_START;
  board_flash_erase_app();
  assert(!board_flash_ok());
  assert(flash_words[(BOARD_FLASH_APP_START + 4096) / 4] == 0x55555555u);
  check_bootloader();

  reset_flash();
  protected_word = BOARD_FLASH_SIZE - 4;
  board_flash_erase_app();
  assert(!board_flash_ok());
  board_flash_init(); // Startup must not discard the erase failure.
  assert(!board_flash_ok());
  accepted = board_flash_write(BOARD_FLASH_APP_START, payload, sizeof(payload));
  assert(!accepted && program_calls == 0);
  check_bootloader();

  reset_flash();
  board_flash_erase_app();
  assert(board_flash_ok());
  for (unsigned i = BOARD_FLASH_APP_START / 4; i < BOARD_FLASH_SIZE / 4; i++) {
    assert(flash_words[i] == 0xe339e339u);
  }
  check_bootloader();
  printf("PASS: 9 CH32V4x7 flash success/fault cases\n\r");
  return 0;
}
