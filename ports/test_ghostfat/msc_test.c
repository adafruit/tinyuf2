// SPDX-License-Identifier: MIT
// Exercise the real MSC callbacks, with no USB controller or flash hardware.
#include "boards.h"
#include "../../src/msc.c"

static uint8_t  sense_key, sense_asc, sense_ascq;
static uint32_t last_indicator;

bool tud_msc_set_sense(uint8_t lun, uint8_t key, uint8_t asc, uint8_t ascq) {
  (void)lun;
  sense_key  = key;
  sense_asc  = asc;
  sense_ascq = ascq;
  return true;
}

void indicator_set(uint32_t state) {
  last_indicator = state;
}

void board_dfu_complete(void) {
  // These tests only invoke completion after a failed update.
  fprintf(stderr, "FAIL: MSC attempted to boot after a flash failure\n\r");
  abort();
}

/** Start an independent host copy with controllable write and flush outcomes. */
static void reset_copy(void) {
  memset(&_wr_state, 0, sizeof(_wr_state));
  test_flash_write_count = test_flash_flush_count = test_flash_fail_on_write = 0;
  test_flash_write_succeeds = test_flash_flush_succeeds = true;
  sense_key = sense_asc = sense_ascq = 0;
  last_indicator                     = STATE_WRITING_STARTED;
}

/** Check the callback's SCSI error and ensure its completion path keeps serving USB. */
static bool write_failed(int32_t result) {
  if (result != -1 || sense_key != SCSI_SENSE_MEDIUM_ERROR || sense_asc != 0x0c || sense_ascq != 0 ||
      !_wr_state.aborted) {
    return false;
  }
  tud_msc_write10_complete_cb(0);
  return last_indicator == STATE_USB_PLUGGED;
}

/** Cover ignored sectors, ordinary writes, mid-command failure and final-flush failure. */
int TestMscWrites(void) {
  UF2_Block blocks[2] = {0};
  reset_copy();
  if (tud_msc_write10_cb(0, 0, 0, (uint8_t *)blocks, sizeof(blocks)) != sizeof(blocks) || test_flash_write_count != 0) {
    return -14;
  }
  for (unsigned i = 0; i < 2; i++) {
    blocks[i].magicStart0 = UF2_MAGIC_START0;
    blocks[i].magicStart1 = UF2_MAGIC_START1;
    blocks[i].magicEnd    = UF2_MAGIC_END;
    blocks[i].flags       = UF2_FLAG_FAMILYID;
    blocks[i].familyID    = BOARD_UF2_FAMILY_ID;
    blocks[i].targetAddr  = 0x1000 + 256 * i;
    blocks[i].payloadSize = 256;
    blocks[i].blockNo     = i;
    blocks[i].numBlocks   = 2;
  }
  int32_t result = tud_msc_write10_cb(0, 0, 0, (uint8_t *)blocks, sizeof(blocks));
  if (result != sizeof(blocks) || test_flash_flush_count != 1 || _wr_state.aborted) {
    return -14;
  }

  reset_copy();
  test_flash_write_succeeds = false;
  result                    = tud_msc_write10_cb(0, 0, 0, (uint8_t *)blocks, 512);
  if (!write_failed(result) || _wr_state.numWritten != 0) {
    return -14;
  }

  reset_copy();
  test_flash_fail_on_write = 2;
  result                   = tud_msc_write10_cb(0, 0, 0, (uint8_t *)blocks, sizeof(blocks));
  if (!write_failed(result) || _wr_state.numWritten != 1 || test_flash_flush_count != 0) {
    return -14;
  }

  reset_copy();
  test_flash_flush_succeeds = false;
  result                    = tud_msc_write10_cb(0, 0, 0, (uint8_t *)blocks, sizeof(blocks));
  if (!write_failed(result) || test_flash_flush_count != 1) {
    return -14;
  }
  // Wrong-family blocks keep the existing ignored-sector behavior too.
  blocks[0].familyID ^= 1u;
  blocks[1].familyID ^= 1u;
  if (tud_msc_write10_cb(0, 0, 0, (uint8_t *)blocks, sizeof(blocks)) != sizeof(blocks)) {
    return -14;
  }
  // Ordinary filesystem metadata is still ignored after a failed UF2 write.
  memset(blocks, 0, sizeof(blocks));
  if (tud_msc_write10_cb(0, 0, 0, (uint8_t *)blocks, sizeof(blocks)) != sizeof(blocks)) {
    return -14;
  }
  reset_copy();
  printf("PASS: MSC write and flush error reporting\n\r");
  return 0;
}
