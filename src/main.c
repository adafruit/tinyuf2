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
#define USE_DFU_BUTTON

#define DFU_DBL_RESET_MAGIC      0x5A1AD5      // SALADS
#define DFU_DBL_RESET_DELAY      500

uint8_t const RGB_USB_UNMOUNTED[] = { 0xff, 0x00, 0x00 }; // Red
uint8_t const RGB_USB_MOUNTED[]   = { 0x00, 0xff, 0x00 }; // Green
uint8_t const RGB_WRITING[]       = { 0xcc, 0x66, 0x00 };
uint8_t const RGB_DOUBLE_TAP[]    = { 0x80, 0x00, 0xff }; // Purple
uint8_t const RGB_UNKNOWN[]       = { 0x00, 0x00, 0x88 }; // for debug
uint8_t const RGB_OFF[]           = { 0x00, 0x00, 0x00 };

//--------------------------------------------------------------------+
//
//--------------------------------------------------------------------+

// defined by linker script
extern uint32_t _board_dfu_dbl_tap[];

static volatile uint32_t _timer_count = 0;


void indicator_set(uint32_t state);

// return true if start DFU mode, else App mode
static bool check_dfu_mode(void)
{
  // invalid app
  if ( !board_app_valid() ) true;

#if USE_DFU_DOUBLE_TAP
  TU_LOG1_HEX(_board_dfu_dbl_tap);
  TU_LOG1_HEX(_board_dfu_dbl_tap[0]);

  if (_board_dfu_dbl_tap[0] == DFU_DBL_RESET_MAGIC)
  {
    TU_LOG1_LOCATION();

    // Double tap occurred
    _board_dfu_dbl_tap[0] = 0;
    return true;
  }

  // Register our first reset for double reset detection
  _board_dfu_dbl_tap[0] = DFU_DBL_RESET_MAGIC;
  _timer_count = 0;

  // Turn on LED/RGB for visual indicator
  board_led_write(0xff);
  board_rgb_write(RGB_DOUBLE_TAP);

  // delay a fraction of second if Reset pin is tap during this delay --> we will enter dfu
  board_timer_start(DFU_DBL_RESET_DELAY/10);
  while(_timer_count < 10) {}
  board_timer_stop();

  // Turn off indicator
  board_led_write(0x00);

  _board_dfu_dbl_tap[0] = 0;
#endif

  return false;
}

int main(void)
{
  board_init();

  // if not DFU mode, jump to App
  if ( !check_dfu_mode() )
  {
    TU_LOG1_LOCATION();
    board_app_jump();
  }

  TU_LOG1_LOCATION();

  board_dfu_init();
  tusb_init();

  board_flash_init();
  uf2_init();

  indicator_set(STATE_BOOTLOADER_STARTED);

#if USE_SCREEN
  screen_init();
  screen_draw_drag();
#endif

#if CFG_TUSB_OS == OPT_OS_NONE
  while(1)
  {
    tud_task();
  }
#endif
}

//--------------------------------------------------------------------+
// Device callbacks
//--------------------------------------------------------------------+

// Invoked when device is mounted
void tud_mount_cb(void)
{
  indicator_set(STATE_USB_MOUNTED);
}

// Invoked when device is unmounted
void tud_umount_cb(void)
{
  indicator_set(STATE_USB_UNMOUNTED);
}

// Invoked when usb bus is suspended
// remote_wakeup_en : if host allow us  to perform remote wakeup
// Within 7ms, device must draw an average of current less than 2.5 mA from bus
void tud_suspend_cb(bool remote_wakeup_en)
{
  (void) remote_wakeup_en;
}

// Invoked when usb bus is resumed
void tud_resume_cb(void)
{
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

void indicator_set(uint32_t state)
{
  _indicator_state = state;
  switch(state)
  {
    case STATE_BOOTLOADER_STARTED:
    case STATE_USB_UNMOUNTED:
      board_rgb_write(RGB_USB_UNMOUNTED);
    break;

    case STATE_USB_MOUNTED:
      board_rgb_write(RGB_USB_MOUNTED);
    break;

    case STATE_WRITING_STARTED:
      board_timer_start(50);
    break;

    case STATE_WRITING_FINISHED:
      board_timer_stop();
      board_rgb_write(RGB_WRITING);
    break;

    default:
      board_rgb_write(RGB_UNKNOWN);
    break;
  }
}


void board_timer_handler(void)
{
  _timer_count++;

  if ( _indicator_state == STATE_WRITING_STARTED )
  {
#if CFG_TUSB_MCU == OPT_MCU_ESP32S2
    if ( _timer_count & 0x01 )
    {
      board_rgb_write(RGB_WRITING);
    }else
    {
      board_rgb_write(RGB_OFF);
    }
#else
    board_led_write(_timer_count & 0x01);
#endif
  }
}

//--------------------------------------------------------------------+
// Logger newlib retarget
//--------------------------------------------------------------------+

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
