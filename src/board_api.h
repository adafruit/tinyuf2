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

// Use LED for part of indicator
#ifndef TINYUF2_LED
#define TINYUF2_LED 0
#endif

// Use Double Tap method to enter DFU mode
#ifndef TINYUF2_DFU_DOUBLE_TAP
#define TINYUF2_DFU_DOUBLE_TAP      0
#endif

// Force boot to DFU mode when button is pressed
#ifndef TINYUF2_DFU_BUTTON
#define TINYUF2_DFU_BUTTON 0
// Should holding the DFU button perform an erase as well?
#  ifndef TINYUF2_DFU_BUTTON_ERASE
#    define TINYUF2_DFU_BUTTON_ERASE 0
#  endif
#endif


// Use Display to draw DFU image
#ifndef TINYUF2_DISPLAY
#define TINYUF2_DISPLAY 0
#endif

// Write protection for bootloader
#ifndef TINYUF2_PROTECT_BOOTLOADER
#define TINYUF2_PROTECT_BOOTLOADER  0
#endif

// Use favicon.ico + autorun.inf (only works with windows)
// define TINYUF2_FAVICON_HEADER to enable this feature

//--------------------------------------------------------------------+
// Constant
//--------------------------------------------------------------------+

#define DBL_TAP_MAGIC            0xf01669ef // Enter DFU magic
#define DBL_TAP_MAGIC_QUICK_BOOT 0xf02669ef // Skip double tap delay detection
#define DBL_TAP_MAGIC_ERASE_APP  0xf5e80ab4 // Erase entire application !!

//--------------------------------------------------------------------+
// Basic API
//--------------------------------------------------------------------+

// Baudrate for UART if used
#define BOARD_UART_BAUDRATE   115200

// Init basic peripherals such as clock, led indicator control (gpio, pwm etc ..)
// This API does not init usb which is only init if DFU is entered
void board_init(void);

// opposite to board_init(), reset all board peripherals. Is called before jumping to application
// TODO force this API in the future
void board_teardown(void) __attribute__ ((weak));

// Reset board, not return
void board_reset(void);

// Write PWM duty value to LED
void board_led_write(uint32_t value);

#if TINYUF2_DFU_BUTTON
  // Read button.  Return true if pressed
  int board_button_read(void);
#endif

// Write color to rgb strip
void board_rgb_write(uint8_t const rgb[]);

// Init uart hardware
void board_uart_init(uint32_t baud_rate);

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

// Init USB hardware (not used for now)
void board_usb_init(void);

// Init DFU process, mostly for starting USB
void board_dfu_init(void);

// DFU is complete, should reset or jump to application mode and not return
void board_dfu_complete(void);

// Fill Serial Number and return its length (limit to 16 bytes)
uint8_t board_usb_get_serial(uint8_t serial_id[16]);

//--------------------------------------------------------------------+
// Flash API
//--------------------------------------------------------------------+

// Initialize flash for DFU
void board_flash_init(void);

// Get size of flash
uint32_t board_flash_size(void);

// Read from flash
void board_flash_read (uint32_t addr, void* buffer, uint32_t len);

// Write to flash
void board_flash_write(uint32_t addr, void const *data, uint32_t len);

// Flush/Sync flash contents
void board_flash_flush(void);

// Erase application
void board_flash_erase_app(void);

// Protect bootloader in flash
bool board_flash_protect_bootloader(bool protect);

//--------------------------------------------------------------------+
// Dispaly API
//--------------------------------------------------------------------+

#if TINYUF2_DISPLAY
void board_display_init(void);
void board_display_draw_line(int y, uint16_t* pixel_color, uint32_t pixel_num);

void screen_draw_drag(void);
#endif

// perform self-update on bootloader
void board_self_update(const uint8_t * bootloader_bin, uint32_t bootloader_len);

//--------------------------------------------------------------------+
// LOG
//--------------------------------------------------------------------+

#define TUF2_VERIFY(_cond)    do \
{                                \
  if (!(_cond)) return false;    \
} while(0)

#define TUF2_ASSERT(_cond)    do                               \
{                                                              \
  if (!(_cond)) {                                              \
    TUF2_LOG1("%s %d: ASSERT FAILED\r\n", __func__, __LINE__); \
    return false;                                              \
  }                                                            \
} while(0)

#if TUF2_LOG

#include <stdio.h>

#ifndef tuf2_printf
#define tuf2_printf printf
#endif

// Log with debug level 1
#define TUF2_LOG1               tuf2_printf
#define TUF2_LOG1_MEM           // tu_print_mem
#define TUF2_LOG1_VAR(_x)       // tu_print_var((uint8_t const*)(_x), sizeof(*(_x)))
#define TUF2_LOG1_INT(_x)       tuf2_printf(#_x " = %ld\r\n", (uint32_t) (_x) )
#define TUF2_LOG1_HEX(_x)       tuf2_printf(#_x " = %lX\r\n", (uint32_t) (_x) )
#define TUF2_LOG1_LOCATION()    tuf2_printf("%s: %d:\r\n", __PRETTY_FUNCTION__, __LINE__)
#define TUF2_LOG1_FAILED()      tuf2_printf("%s: %d: Failed\r\n", __PRETTY_FUNCTION__, __LINE__)

// Log with debug level 2
#if CFG_TUSB_DEBUG > 1
  #define TUF2_LOG2             TUF2_LOG1
  #define TUF2_LOG2_MEM         TUF2_LOG1_MEM
  #define TUF2_LOG2_VAR         TUF2_LOG1_VAR
  #define TUF2_LOG2_INT         TUF2_LOG1_INT
  #define TUF2_LOG2_HEX         TUF2_LOG1_HEX
  #define TUF2_LOG2_LOCATION()  TUF2_LOG1_LOCATION()
#endif

#endif // TUF2_LOG

#ifndef TUF2_LOG1
  #define TUF2_LOG1(...)
  #define TUF2_LOG1_MEM(...)
  #define TUF2_LOG1_VAR(...)
  #define TUF2_LOG1_INT(...)
  #define TUF2_LOG1_HEX(...)
  #define TUF2_LOG1_LOCATION()
  #define TUF2_LOG1_FAILED()
#endif

#ifndef TUF2_LOG2
  #define TUF2_LOG2(...)
  #define TUF2_LOG2_MEM(...)
  #define TUF2_LOG2_VAR(...)
  #define TUF2_LOG2_INT(...)
  #define TUF2_LOG2_HEX(...)
  #define TUF2_LOG2_LOCATION()
#endif

//--------------------------------------------------------------------+
// not part of board API, move to its own file later
//--------------------------------------------------------------------+

enum {
  STATE_BOOTLOADER_STARTED = 0,///< STATE_BOOTLOADER_STARTED
  STATE_USB_PLUGGED,           ///< STATE_USB_PLUGGED
  STATE_USB_UNPLUGGED,         ///< STATE_USB_UNPLUGGED
  STATE_WRITING_STARTED,       ///< STATE_WRITING_STARTED
  STATE_WRITING_FINISHED,      ///< STATE_WRITING_FINISHED
};

void indicator_set(uint32_t state);

static inline void rgb_brightness(uint8_t out[3], uint8_t const in[3], uint8_t brightness)
{
  for(uint32_t i=0; i<3; i++ )
  {
    out[i] = (in[i]*brightness) >> 8;
  }
}

//--------------------------------------------------------------------+
//
//--------------------------------------------------------------------+
#define ST_CMD_DELAY 0x80 // special signifier for command lists

#define ST77XX_NOP 0x00
#define ST77XX_SWRESET 0x01
#define ST77XX_RDDID 0x04
#define ST77XX_RDDST 0x09

#define ST77XX_SLPIN 0x10
#define ST77XX_SLPOUT 0x11
#define ST77XX_PTLON 0x12
#define ST77XX_NORON 0x13

#define ST77XX_INVOFF 0x20
#define ST77XX_INVON 0x21
#define ST77XX_DISPOFF 0x28
#define ST77XX_DISPON 0x29
#define ST77XX_CASET 0x2A
#define ST77XX_RASET 0x2B
#define ST77XX_RAMWR 0x2C
#define ST77XX_RAMRD 0x2E

#define ST77XX_PTLAR 0x30
#define ST77XX_TEOFF 0x34
#define ST77XX_TEON 0x35
#define ST77XX_MADCTL 0x36
#define ST77XX_COLMOD 0x3A

#define ST77XX_RDID1 0xDA
#define ST77XX_RDID2 0xDB
#define ST77XX_RDID3 0xDC
#define ST77XX_RDID4 0xDD

#define TFT_MADCTL_MY  0x80  ///< Page addr order: Bottom to top
#define TFT_MADCTL_MX  0x40  ///< Column addr order: Right to left
#define TFT_MADCTL_MV  0x20  ///< Page/Column order: Reverse Mode ( X <-> Y )

#define TFT_MADCTL_ML  0x10  ///< LCD refresh Bottom to top
#define TFT_MADCTL_MH  0x04  ///< LCD refresh right to left

#define TFT_MADCTL_RGB 0x00  ///< Red-Green-Blue pixel order
#define TFT_MADCTL_BGR 0x08  ///< Blue-Green-Red pixel order

#endif
