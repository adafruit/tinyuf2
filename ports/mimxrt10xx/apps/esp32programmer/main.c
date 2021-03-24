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

#include "fsl_gpio.h"
#include "fsl_iomuxc.h"

#include "board_api.h"
#include "tusb.h"

/* This is an application to act as USB <-> Uart and
 * used to program ESP32 Co-Processors
 */

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM DECLARATION
//--------------------------------------------------------------------+

// TODO ESP32 pindef for Metro M7 1011, move to board.h later
#define ESP_GPIO0_PINMUX  IOMUXC_GPIO_SD_05_GPIO2_IO05
#define ESP_GPIO0_PORT    GPIO2
#define ESP_GPIO0_PIN     5

#define ESP_RESET_PINMUX  IOMUXC_GPIO_AD_07_GPIOMUX_IO21
#define ESP_RESET_PORT    GPIO1
#define ESP_RESET_PIN     21

static volatile uint32_t _timer_count = 0;

int main(void)
{
  board_init();

  TUF2_LOG1("ESP32 Programmer Firmware\r\n");
  gpio_pin_config_t pin_config = { kGPIO_DigitalOutput, 0, kGPIO_NoIntmode };

  // ESP GPIO0
  IOMUXC_SetPinMux(ESP_GPIO0_PINMUX, 0U);
  IOMUXC_SetPinConfig(ESP_GPIO0_PINMUX, 0x10B0U);
  GPIO_PinInit(ESP_GPIO0_PORT, ESP_GPIO0_PIN, &pin_config);

  // ESP Reset
  IOMUXC_SetPinMux(ESP_RESET_PINMUX, 0U);
  IOMUXC_SetPinConfig(ESP_RESET_PINMUX, 0x10B0U);
  GPIO_PinInit(ESP_RESET_PORT, ESP_RESET_PIN, &pin_config);

  // Put ESP into upload mode
  GPIO_PinWrite(ESP_GPIO0_PORT, ESP_GPIO0_PIN, 0);

  // Reset ESP in 100 ms
  GPIO_PinWrite(ESP_RESET_PORT, ESP_RESET_PIN, 0);

  _timer_count = 0;
  board_timer_start(1);
  while(_timer_count < 100) {}
  board_timer_stop();

  GPIO_PinWrite(ESP_RESET_PORT, ESP_RESET_PIN, 1);

  board_usb_init();
  tusb_init();

  while(1)
  {
    tud_task();
  }
}

void board_timer_handler(void)
{
  _timer_count++;
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
