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

#ifndef BOARDS_H
#define BOARDS_H

#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include "boards.h"

//--------------------------------------------------------------------+
// Features
//--------------------------------------------------------------------+

// Flash Start Address of Application
#ifndef BOARD_FLASH_APP_START
#define BOARD_FLASH_APP_START  0
#endif

// Use RGB for indicator e.g neopixel, dotstar
// 0 for not available, otherwise number of RGBs
#ifndef USE_RGB
#define USE_RGB 0
#endif

// Baudrate for UART if used
#define BOARD_UART_BAUDRATE   115200

void board_init(void);

// Turn on or off the LED
void board_led_write(uint32_t state);

// Write color to rgb strip
void board_rgb_write(uint8_t const rgb[]);

// Send characters to UART for debugging
int board_uart_write(void const * buf, int len);

// start timer with ms interval
void board_timer_start(uint32_t ms);

// stop timer
void board_timer_stop(void);

// timer event handler, must be called by port/board
extern void board_timer_handler(void);

// Check if application is valid
bool board_app_valid(void);

// Jump to Application
void board_app_jump(void);

// Init DFU process
void board_dfu_init(void);

// DFU is complete, should reset or jump to application mode
void board_dfu_complete(void);

// Fill Serial Number and return its length (limit to 16 bytes)
uint8_t board_usb_get_serial(uint8_t serial_id[16]);

//------------- Flash -------------//
void     board_flash_init(void);
uint32_t board_flash_size(void);

void     board_flash_read (uint32_t addr, void* buffer, uint32_t len);
void     board_flash_write(uint32_t addr, void const *data, uint32_t len);
void     board_flash_flush(void);


#ifdef PIN_DISPLAY_SCK
  #define USE_SCREEN 1

  void screen_init(void);
  void screen_draw_drag(void);
  void screen_draw_hf2(void);
#else
  #define USE_SCREEN 0
#endif


//--------------------------------------------------------------------+
// not part of board API, move to its own file later
//--------------------------------------------------------------------+

enum {
  STATE_BOOTLOADER_STARTED = 0,
  STATE_USB_MOUNTED,
  STATE_USB_UNMOUNTED,
  STATE_WRITING_STARTED,
  STATE_WRITING_FINISHED,
};

void indicator_set(uint32_t state);

#endif
