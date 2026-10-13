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

#ifndef DFU_RUNTIME_H_
#define DFU_RUNTIME_H_

#include <stdbool.h>
#include <stdint.h>

// Optional block a UF2 may carry past the image to label one copy of the app: magic, nonce length (LE, 1..16),
// nonce, then every remaining byte equal to its offset in the block. A valid block makes the DFU runtime
// interface string "HIL <nonce in hex>".
#define NONCE_BLOCK_MAGIC     "TUF2NONC"
#define NONCE_BLOCK_SIZE      256
#define NONCE_MAX_LEN         16
#define NONCE_STRING_SIZE     (sizeof("HIL ") + 2 * NONCE_MAX_LEN)

// Reboot into TinyUF2 DFU mode, no return
void board_reboot_to_bootloader(void);

// Read the nonce block from where the port keeps it; false when it cannot be read
bool board_nonce_block_read(uint8_t block[NONCE_BLOCK_SIZE]);

// "HIL <nonce in hex>" into str when the block is valid; str is left untouched otherwise
bool nonce_block_to_string(uint8_t const block[NONCE_BLOCK_SIZE], char str[NONCE_STRING_SIZE]);

#endif
