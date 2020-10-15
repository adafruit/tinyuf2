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

#include "tusb.h"
#include "board.h"

enum {
  STATE_BOOTLOADER_STARTED = 0,
  STATE_USB_MOUNTED,
  STATE_USB_UNMOUNTED,
  STATE_WRITING_STARTED,
  STATE_WRITING_FINISHED,
};

void board_init(void);
void board_teardown(void);
void board_led_state(uint32_t state);


#ifdef PIN_DISPLAY_SCK
  #define USE_SCREEN 1

  void screen_init(void);
  void screen_draw_drag(void);
  void screen_draw_hf2(void);
#else
  #define USE_SCREEN 0
#endif

#if CFG_TUSB_MCU == OPT_MCU_ESP32S2
// Debug helper, remove later
#include "esp_log.h"
#define PRINTF(...)           ESP_LOGI("uf2", __VA_ARGS__)
#define PRINT_LOCATION()      ESP_LOGI("uf2", "%s: %d", __PRETTY_FUNCTION__, __LINE__)
#define PRINT_MESS(x)         ESP_LOGI("uf2", "%s", (char*)(x))
#define PRINT_STR(x)          ESP_LOGI("uf2", #x " = %s"   , (char*)(x) )
#define PRINT_INT(x)          ESP_LOGI("uf2", #x " = %d"  , (int32_t) (x) )
#define PRINT_HEX(x)          ESP_LOGI("uf2", #x " = 0x%X", (uint32_t) (x) )

#define PRINT_BUFFER(buf, n) \
  do {\
    uint8_t const* p8 = (uint8_t const*) (buf);\
    printf(#buf ": ");\
    for(uint32_t i=0; i<(n); i++) printf("%x ", p8[i]);\
    printf("\n");\
  }while(0)

#endif

#endif
