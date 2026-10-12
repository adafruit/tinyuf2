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

#include <string.h>
#include "dfu_runtime.h"

bool nonce_block_to_string(uint8_t const block[NONCE_BLOCK_SIZE], char str[NONCE_STRING_SIZE]) {
  if (memcmp(block, NONCE_BLOCK_MAGIC, 8) != 0) {
    return false;
  }

  uint32_t const len = block[8] | (block[9] << 8) | ((uint32_t) block[10] << 16) | ((uint32_t) block[11] << 24);
  if (len == 0 || len > NONCE_MAX_LEN) {
    return false;
  }
  for (uint32_t i = 12 + len; i < NONCE_BLOCK_SIZE; i++) {
    if (block[i] != (uint8_t) i) {
      return false;
    }
  }

  static const char hex[] = "0123456789abcdef";
  memcpy(str, "HIL ", 4);
  str += 4;
  for (uint32_t i = 0; i < len; i++) {
    *str++ = hex[block[12 + i] >> 4];
    *str++ = hex[block[12 + i] & 0xf];
  }
  *str = '\0';
  return true;
}
