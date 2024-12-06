/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2019 Ha Thach (tinyusb.org)
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
 *
 */

#include <stdlib.h>
#include <stdio.h>
#include <stdbool.h>
#include <string.h>

#include "board_api.h"
#include "uf2.h"
#include "tusb.h"

//--------------------------------------------------------------------+
// MACRO CONSTANT TYPEDEF PROTOTYPES
//--------------------------------------------------------------------+
//#define USE_DFU_BUTTON    1

#ifndef NEOPIXEL_INVERT_RG
uint8_t RGB_USB_UNMOUNTED[] = { 0xff, 0x00, 0x00 }; // Red
uint8_t RGB_USB_MOUNTED[]   = { 0x00, 0xff, 0x00 }; // Green
uint8_t RGB_WRITING[]       = { 0xcc, 0x66, 0x00 };
uint8_t RGB_DOUBLE_TAP[]    = { 0x80, 0x00, 0xff }; // Purple
#else
uint8_t RGB_USB_UNMOUNTED[] = { 0x00, 0xff, 0x00 }; // Red
uint8_t RGB_USB_MOUNTED[]   = { 0xff, 0x00, 0x00 }; // Green
uint8_t RGB_WRITING[]       = { 0x66, 0xcc, 0x00 };
uint8_t RGB_DOUBLE_TAP[]    = { 0x00, 0x80, 0xff }; // Purple
#endif
uint8_t RGB_UNKNOWN[]       = { 0x00, 0x00, 0x88 }; // for debug
uint8_t RGB_OFF[]           = { 0x00, 0x00, 0x00 };

static volatile uint32_t _timer_count = 0;

//--------------------------------------------------------------------+
//
//--------------------------------------------------------------------+
static bool check_dfu_mode(void);

int main(void) {
  board_init();
  if (board_init2) board_init2();
  TUF2_LOG1("TinyUF2\r\n");

#if TINYUF2_PROTECT_BOOTLOADER
  board_flash_protect_bootloader(true);
#endif

  // if not DFU mode, jump to App
  if (!check_dfu_mode()) {
    TUF2_LOG1("Jump to application\r\n");
    if (board_teardown) board_teardown();
    if (board_teardown2) board_teardown2();
    board_app_jump();
    TUF2_LOG1("Failed to jump\r\n");
    while (1) {}
  }

  TUF2_LOG1("Start DFU mode\r\n");
  board_dfu_init();
  board_flash_init();
  uf2_init();

  tud_init(BOARD_TUD_RHPORT);

  indicator_set(STATE_USB_UNPLUGGED);

#if TINYUF2_DISPLAY
  board_display_init();
  screen_draw_drag();
#endif

#if CFG_TUSB_OS == OPT_OS_NONE || CFG_TUSB_OS == OPT_OS_PICO
  while(1) {
    tud_task();
  }
#endif
}

// return true if start DFU mode, else App mode
static bool check_dfu_mode(void) {
  // Check if app is valid
  if (!board_app_valid()) {
    TUF2_LOG1("App invalid\r\n");
    return true;
  }
  if (board_app_valid2 && !board_app_valid2()) {
    TUF2_LOG1("App invalid\r\n");
    return true;
  }

#if TINYUF2_DBL_TAP_DFU
   TUF2_LOG1_HEX(TINYUF2_DBL_TAP_REG);

  switch(TINYUF2_DBL_TAP_REG) {
    case DBL_TAP_MAGIC_QUICK_BOOT:
      // Boot to app quickly
      TUF2_LOG1("Quick boot to App\r\n");
      TINYUF2_DBL_TAP_REG = 0;
      return false;

    case DBL_TAP_MAGIC:
      // Double tap occurred
      TUF2_LOG1("Double Tap Reset\r\n");
      TINYUF2_DBL_TAP_REG = 0;
      return true;

    case DBL_TAP_MAGIC_ERASE_APP:
      TUF2_LOG1("Erase app\r\n");
      TINYUF2_DBL_TAP_REG = 0;
      indicator_set(STATE_WRITING_STARTED);
      board_flash_erase_app();
      indicator_set(STATE_WRITING_FINISHED);
      return true;

    default:
      break;
  }

  // Register our first reset for double reset detection
  TINYUF2_DBL_TAP_REG = DBL_TAP_MAGIC;

  _timer_count = 0;
  board_timer_start(1);

  // neopixel may need a bit of prior delay to work
  // while(_timer_count < 1) {}

  // Turn on LED/RGB for visual indicator
  board_led_write(0xff);
  board_rgb_write(RGB_DOUBLE_TAP);

  // delay a fraction of second if Reset pin is tap during this delay --> we will enter dfu
  while(_timer_count < TINYUF2_DBL_TAP_DELAY) {}
  board_timer_stop();

  // Turn off indicator
  board_rgb_write(RGB_OFF);
  board_led_write(0x00);

  TINYUF2_DBL_TAP_REG = 0;
#endif

  return false;
}

//--------------------------------------------------------------------+
// Device callbacks
//--------------------------------------------------------------------+

// Invoked when device is plugged and configured
void tud_mount_cb(void) {
  indicator_set(STATE_USB_PLUGGED);
}

// Invoked when device is unplugged
void tud_umount_cb(void) {
  indicator_set(STATE_USB_UNPLUGGED);
}

//--------------------------------------------------------------------+
// Indicator
//--------------------------------------------------------------------+

static uint32_t indicator_state = STATE_BOOTLOADER_STARTED;
static uint8_t indicator_rgb[3];

void indicator_set(uint32_t state) {
  indicator_state = state;
  switch (state) {
    case STATE_USB_UNPLUGGED:
      board_timer_start(1);
      memcpy(indicator_rgb, RGB_USB_UNMOUNTED, 3);
      board_rgb_write(indicator_rgb);
      break;

    case STATE_USB_PLUGGED:
      board_timer_start(5);
      memcpy(indicator_rgb, RGB_USB_MOUNTED, 3);
      board_rgb_write(indicator_rgb);
      break;

    case STATE_WRITING_STARTED:
      board_timer_start(25);
      memcpy(indicator_rgb, RGB_WRITING, 3);
      break;

    case STATE_WRITING_FINISHED:
      board_timer_stop();
      board_rgb_write(RGB_WRITING);
      break;

    default:
      break; // nothing to do
  }
}

void board_timer_handler(void) {
  _timer_count++;

  switch (indicator_state) {
    case STATE_USB_UNPLUGGED:
    case STATE_USB_PLUGGED: {
      // Fading with LED TODO option to skip for unsupported MCUs
      uint8_t duty = _timer_count & 0xff;
      if (_timer_count & 0x100) duty = 255 - duty;
      board_led_write(duty);

      // Skip RGB fading since it is too similar to CircuitPython
      // uint8_t rgb[3];
      // rgb_brightness(rgb, _indicator_rgb, duty);
      // board_rgb_write(rgb);
      break;
    }

    case STATE_WRITING_STARTED: {
      // Fast toggle with both LED and RGB
      bool is_on = _timer_count & 0x01;

      // fast blink LED if available
      board_led_write(is_on ? 0xff : 0x000);

      // blink RGB if available
      board_rgb_write(is_on ? indicator_rgb : RGB_OFF);
      break;
    }

    default:
      break; // nothing to do
  }
}

//--------------------------------------------------------------------+
// Logger newlib retarget
//--------------------------------------------------------------------+

// Enable only with LOG is enabled (Note: ESP32-S2 has built-in support already)
#if (CFG_TUSB_DEBUG || TUF2_LOG) && (CFG_TUSB_MCU != OPT_MCU_ESP32S2 && CFG_TUSB_MCU != OPT_MCU_RP2040)
#if defined(LOGGER_RTT)
#include "SEGGER_RTT.h"
#endif

TU_ATTR_USED int _write (int fhdl, const void *buf, size_t count) {
  (void) fhdl;

#if defined(LOGGER_RTT)
  SEGGER_RTT_Write(0, (char*) buf, (int) count);
  return count;
#else
  return board_uart_write(buf, count);
#endif
}

#endif
