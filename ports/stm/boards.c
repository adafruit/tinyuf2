/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2018 Ha Thach for Adafruit Industries
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

#include "boards.h"

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM DECLARATION
//--------------------------------------------------------------------+

#define RGB_USB_UNMOUNTED   0xff, 0x00, 0x00 // Red
#define RGB_USB_MOUNTED     0x00, 0xff, 0x00 // Green
#define RGB_WRITING         0xcc, 0x66, 0x00
#define RGB_UNKNOWN         0x00, 0x00, 0x88 // for debug

void board_init(void)
{


}

void board_teardown(void)
{

}

//--------------------------------------------------------------------+
// LED pattern
//--------------------------------------------------------------------+

#ifdef PIN_NEOPIXEL

static void neopixel_set(uint8_t r, uint8_t g, uint8_t b)
{
  (void) r; (void) g; (void) b;
}

//void led_blinky_cb(TimerHandle_t xTimer)
//{
//  (void) xTimer;
//  static bool led_state = false;
//  led_state = 1 - led_state; // toggle
//
//  if ( led_state )
//  {
//    neopixel_set(RGB_WRITING);
//  }else
//  {
//    strip->clear(strip, 100);
//  }
//}
#endif

void board_led_state(uint32_t state)
{
  #ifdef PIN_NEOPIXEL
  switch(state)
  {
    case STATE_BOOTLOADER_STARTED:
    case STATE_USB_UNMOUNTED:
      neopixel_set(RGB_USB_UNMOUNTED);
    break;

    case STATE_USB_MOUNTED:
      neopixel_set(RGB_USB_MOUNTED);
    break;

    case STATE_WRITING_STARTED:
      // soft timer for blinky
//      blinky_tm = xTimerCreate(NULL, pdMS_TO_TICKS(50), true, NULL, led_blinky_cb);
//      xTimerStart(blinky_tm, 0);
    break;

    case STATE_WRITING_FINISHED:
//      xTimerStop(blinky_tm, 0);
      neopixel_set(RGB_WRITING);
    break;

    default:
      neopixel_set(RGB_UNKNOWN);
    break;
  }
  #endif
}

// Required by __libc_init_array in startup code if we are compiling using
// -nostdlib/-nostartfiles.
void _init(void)
{

}
