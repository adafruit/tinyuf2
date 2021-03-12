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
// MACRO CONSTANT TYPEDEF PROTYPES
//--------------------------------------------------------------------+
//#define USE_DFU_BUTTON    1

// Enter DFU magic
#define DBL_TAP_MAGIC             0xf01669ef

// Skip double tap delay detction
#define DBL_TAP_MAGIC_QUICK_BOOT  0xf02669ef

// timeout for double tap detection
#define DBL_TAP_DELAY             500

uint8_t const RGB_USB_UNMOUNTED[] = { 0xff, 0x00, 0x00 }; // Red
uint8_t const RGB_USB_MOUNTED[]   = { 0x00, 0xff, 0x00 }; // Green
uint8_t const RGB_WRITING[]       = { 0xcc, 0x66, 0x00 };
uint8_t const RGB_DOUBLE_TAP[]    = { 0x80, 0x00, 0xff }; // Purple
uint8_t const RGB_UNKNOWN[]       = { 0x00, 0x00, 0x88 }; // for debug
uint8_t const RGB_OFF[]           = { 0x00, 0x00, 0x00 };

//--------------------------------------------------------------------+
//
//--------------------------------------------------------------------+

#ifndef DBL_TAP_REG 
// defined by linker script
extern uint32_t _board_dfu_dbl_tap[];
#define DBL_TAP_REG   _board_dfu_dbl_tap[0]
#endif
static volatile uint32_t _timer_count = 0;

bool _dfu_complete = false;

// return true if start DFU mode, else App mode
static bool check_dfu_mode(void)
{
  // Check if app is valid
  if ( !board_app_valid() ) return true;

#if TINYUF2_DFU_DOUBLE_TAP
//  TU_LOG1_HEX(DBL_TAP_REG);

  // App want to reboot quickly
  if (DBL_TAP_REG == DBL_TAP_MAGIC_QUICK_BOOT)
  {
    DBL_TAP_REG = 0;
    return false;
  }

  if (DBL_TAP_REG == DBL_TAP_MAGIC)
  {
    // Double tap occurred
    DBL_TAP_REG = 0;
    return true;
  }

  // Register our first reset for double reset detection
  DBL_TAP_REG = DBL_TAP_MAGIC;

  _timer_count = 0;
  board_timer_start(1);

  // neopixel may need a bit of prior delay to work
  // while(_timer_count < 1) {}

  // Turn on LED/RGB for visual indicator
  board_led_write(0xff);
  board_rgb_write(RGB_DOUBLE_TAP);

  // delay a fraction of second if Reset pin is tap during this delay --> we will enter dfu
  while(_timer_count < DBL_TAP_DELAY) {}
  board_timer_stop();

  // Turn off indicator
  board_rgb_write(RGB_OFF);
  board_led_write(0x00);

  DBL_TAP_REG = 0;
#endif

  return false;
}

int main(void)
{
  board_init();
  TU_LOG1("TinyUF2\r\n");

  // if not DFU mode, jump to App
  if ( !check_dfu_mode() )
  {
    board_app_jump();
    while(1) {}
  }

  board_dfu_init();
  board_flash_init();
  uf2_init();
  tusb_init();

  indicator_set(STATE_USB_UNPLUGGED);

#if TINYUF2_DISPLAY
  board_display_init();
  screen_draw_drag();
#endif

#if (CFG_TUSB_OS == OPT_OS_NONE || CFG_TUSB_OS == OPT_OS_PICO)
  while(1)
  {
    tud_task();
    if (_dfu_complete)
    {
      board_dfu_complete();
	  
      // _dfu_complete = false;
      // board_dfu_complete() should not return
      // getting here is an indicator of error
      while(1) {}
    }
  }
#endif
}

//--------------------------------------------------------------------+
// Device callbacks
//--------------------------------------------------------------------+

// Invoked when device is plugged and configured
void tud_mount_cb(void)
{
  indicator_set(STATE_USB_PLUGGED);
}

// Invoked when device is unplugged
void tud_umount_cb(void)
{
  indicator_set(STATE_USB_UNPLUGGED);
}

//--------------------------------------------------------------------+
// USB HID
//--------------------------------------------------------------------+

// Invoked when received GET_REPORT control request
// Application must fill buffer report's content and return its length.
// Return zero will cause the stack to STALL request
uint16_t tud_hid_get_report_cb(uint8_t report_id, hid_report_type_t report_type, uint8_t* buffer, uint16_t reqlen)
{
  // TODO not Implemented
  (void) report_id;
  (void) report_type;
  (void) buffer;
  (void) reqlen;

  return 0;
}

// Invoked when received SET_REPORT control request or
// received data on OUT endpoint ( Report ID = 0, Type = 0 )
void tud_hid_set_report_cb(uint8_t report_id, hid_report_type_t report_type, uint8_t const* buffer, uint16_t bufsize)
{
  // This example doesn't use multiple report and report ID
  (void) report_id;
  (void) report_type;
  (void) buffer;
  (void) bufsize;
}

//--------------------------------------------------------------------+
// Indicator
//--------------------------------------------------------------------+

static uint32_t _indicator_state = STATE_BOOTLOADER_STARTED;
static uint8_t _indicator_rgb[3];

void indicator_set(uint32_t state)
{
  _indicator_state = state;
  switch(state)
  {
    case STATE_USB_UNPLUGGED:
      board_timer_start(1);
      memcpy(_indicator_rgb, RGB_USB_UNMOUNTED, 3);
      board_rgb_write(_indicator_rgb);
    break;

    case STATE_USB_PLUGGED:
      board_timer_start(5);
      memcpy(_indicator_rgb, RGB_USB_MOUNTED, 3);
      board_rgb_write(_indicator_rgb);
    break;

    case STATE_WRITING_STARTED:
      board_timer_start(25);
      memcpy(_indicator_rgb, RGB_WRITING, 3);
    break;

    case STATE_WRITING_FINISHED:
      board_timer_stop();
      board_rgb_write(RGB_WRITING);
    break;

    default: break; // nothing to do
  }
}

void board_timer_handler(void)
{
  _timer_count++;

  switch (_indicator_state)
  {
    case STATE_USB_UNPLUGGED:
    case STATE_USB_PLUGGED:
    {
      // Fading with LED TODO option to skip for unsupported MCUs
      uint8_t duty = _timer_count & 0xff;
      if ( _timer_count & 0x100 ) duty = 255 - duty;
      board_led_write(duty);

      // Skip RGB fading since it is too similar to CircuitPython
      // uint8_t rgb[3];
      // rgb_brightness(rgb, _indicator_rgb, duty);
      // board_rgb_write(rgb);
    }
    break;

    case STATE_WRITING_STARTED:
    {
      // Fast toggle with both LED and RGB
      bool is_on = _timer_count & 0x01;

      // fast blink LED if available
      board_led_write(is_on ? 0xff : 0x000);

      // blink RGB if available
      board_rgb_write(is_on ? _indicator_rgb : RGB_OFF);
    }
    break;

    default: break; // nothing to do
  }
}

//--------------------------------------------------------------------+
// Logger newlib retarget
//--------------------------------------------------------------------+

// Enable only with LOG is enabled (Note: ESP32-S2 has built-in support already)
#if CFG_TUSB_DEBUG && (CFG_TUSB_MCU != OPT_MCU_ESP32S2 && CFG_TUSB_MCU != OPT_MCU_RP2040)

#if defined(LOGGER_RTT)
#include "SEGGER_RTT.h"
#endif

TU_ATTR_USED int _write (int fhdl, const void *buf, size_t count)
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
