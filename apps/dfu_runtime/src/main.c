/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2026 Ha Thach (tinyusb.org) for Adafruit Industries
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
#include "tusb.h"
#include "dfu_runtime.h"

// Example app with a single USB DFU runtime interface: a DFU_DETACH request (e.g. dfu-util -e) reboots into TinyUF2.

// lets the DETACH status stage complete before the device leaves the bus
#define DETACH_REBOOT_DELAY_MS  100

char dfu_rt_string[NONCE_STRING_SIZE] = "DFU runtime";

static volatile uint32_t _ms;
static volatile bool _detached;
static uint32_t _detach_ms;

int main(void) {
  uint8_t block[NONCE_BLOCK_SIZE];
  board_init();
  if (board_nonce_block_read(block)) {
    nonce_block_to_string(block, dfu_rt_string);
  }
  board_dfu_init();
  board_timer_start(1);   // after board_dfu_init(), which may change the clock the tick is derived from
  tud_init(BOARD_TUD_RHPORT);

  while (1) {
    // bounded wait so an RTOS port still reaches the reboot check when the bus goes quiet
    tud_task_ext(10, false);

    if (_detached && (uint32_t) (_ms - _detach_ms) >= DETACH_REBOOT_DELAY_MS) {
      board_reboot_to_bootloader();
    }
  }
}

void board_timer_handler(void) {
  _ms++;
}

// TinyUSB calls this right after queuing the DETACH status stage, before the host has it
void tud_dfu_runtime_reboot_to_dfu_cb(void) {
  _detach_ms = _ms;
  _detached = true;
}
