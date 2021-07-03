/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2020 Ha Thach (tinyusb.org) for Adafruit Industries
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

#include <stdlib.h>
#include <stdio.h>
#include <stdbool.h>
#include <string.h>

#include "board_api.h"

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM DECLARATION
//--------------------------------------------------------------------+

// bootloader binary contents in array bytes
extern const unsigned long bindata_len;
extern const unsigned char bindata[];

uint8_t const RGB_WRITING[]       = { 0xcc, 0x66, 0x00 };
uint8_t const RGB_OFF[]           = { 0x00, 0x00, 0x00 };

static volatile uint32_t _timer_count = 0;

int main(void)
{
  board_init();

  printf("TinyUF2: Self-update\r\n");
  printf("bin data size = %ld\r\n", bindata_len);

  // Set indicator similar to WRITING
  board_timer_start(25);

  // This should never return
  board_self_update((uint8_t const*) bindata, (uint32_t) bindata_len);

  while(1)
  {

  }
}

void board_timer_handler(void)
{
  _timer_count++;

  // Fast toggle with both LED and RGB
  bool is_on = _timer_count & 0x01;

  // fast blink LED if available
  board_led_write(is_on ? 0xff : 0x000);

  // blink RGB if available
  board_rgb_write(is_on ? RGB_WRITING : RGB_OFF);
}

//--------------------------------------------------------------------+
// Logger newlib retarget
//--------------------------------------------------------------------+

// Enable only with LOG is enabled (Note: ESP32-S2 has built-in support already)
#if TUF2_LOG // && (CFG_TUSB_MCU != OPT_MCU_ESP32S2)

#if defined(LOGGER_RTT)
#include "SEGGER_RTT.h"
#endif

__attribute__ ((used)) int _write (int fhdl, const void *buf, size_t count)
{
  (void) fhdl;

#if defined(LOGGER_RTT)
  SEGGER_RTT_Write(0, (char*) buf, (int) count);
  return count;
#else
  return board_uart_write(buf, count);
#endif
}

#endif
