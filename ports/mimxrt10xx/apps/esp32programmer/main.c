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
#include "fsl_lpuart.h"

#include "board_api.h"
#include "tusb.h"

/* This is an application to act as USB <-> Uart and
 * used to program ESP32 Co-Processors
 */

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM DECLARATION
//--------------------------------------------------------------------+
//uint8_t const RGB_USB_UNMOUNTED[] = { 0xff, 0x00, 0x00 }; // Red
//uint8_t const RGB_USB_MOUNTED[]   = { 0x00, 0xff, 0x00 }; // Green

// optional API, not included in board_api.h
int board_uart_read(uint8_t* buf, int len);

static volatile uint32_t _timer_count = 0;
static uint32_t baud_rate = 115200;
static uint8_t serial_buf[512];

static inline void esp32_set_io0(uint8_t state)
{
  GPIO_PinWrite(ESP32_GPIO0_PORT, ESP32_GPIO0_PIN, state);
}

static inline void esp32_set_reset(uint8_t state)
{
  GPIO_PinWrite(ESP32_RESET_PORT, ESP32_RESET_PIN, state);
}

static inline void delay_blocking(uint8_t ms)
{
  uint32_t start = _timer_count;
  while(_timer_count - start < ms)
  {
    tud_task();
  }
}

void esp32_enter_dfu(void)
{
  // Put ESP into upload mode
  esp32_set_io0(0);
  esp32_set_reset(0);
  delay_blocking(100); // delay while reset

  esp32_set_reset(1);
  delay_blocking(100); // delay after reset
  esp32_set_io0(1);
}

int main(void)
{
  board_init();

  gpio_pin_config_t pin_config = { kGPIO_DigitalOutput, 1, kGPIO_NoIntmode };

  // ESP GPIO0
  IOMUXC_SetPinMux(ESP32_GPIO0_PINMUX, 0);
  IOMUXC_SetPinConfig(ESP32_GPIO0_PINMUX, 0x10B0U);
  GPIO_PinInit(ESP32_GPIO0_PORT, ESP32_GPIO0_PIN, &pin_config);

  // ESP Reset
  IOMUXC_SetPinMux(ESP32_RESET_PINMUX, 0);
  IOMUXC_SetPinConfig(ESP32_RESET_PINMUX, 0x10B0U);
  GPIO_PinInit(ESP32_RESET_PORT, ESP32_RESET_PIN, &pin_config);

  board_uart_init(115200);
  board_usb_init();
  tusb_init();

  board_timer_start(1);
  esp32_enter_dfu();
  board_timer_stop();

  while(1)
  {
#if 0
    (void) serial_buf;
#else
    uint32_t count;

    // USB -> UART
    while( tud_cdc_available() )
    {
      board_led_write(0xff);

      count = tud_cdc_read(serial_buf, sizeof(serial_buf));
      board_uart_write(serial_buf, count);

      board_led_write(0);
    }

    // UART -> USB
    count = (uint32_t) board_uart_read(serial_buf, sizeof(serial_buf));
    if (count)
    {
      board_led_write(0xff);

      tud_cdc_write(serial_buf, count);
      tud_cdc_write_flush();

      board_led_write(0);
    }
#endif

    tud_task();
  }
}

void board_timer_handler(void)
{
  _timer_count++;
}

//--------------------------------------------------------------------+
// USB CDC
//--------------------------------------------------------------------+

// Invoked when device is plugged and configured
//void tud_mount_cb(void)
//{
//  board_rgb_write(RGB_USB_MOUNTED);
//}
//
//// Invoked when device is unplugged
//void tud_umount_cb(void)
//{
//  board_rgb_write(RGB_USB_UNMOUNTED);
//}

// Invoked when line coding is change via SET_LINE_CODING
void tud_cdc_line_coding_cb(uint8_t itf, cdc_line_coding_t const* line_coding)
{
  (void) itf;

  if ( baud_rate != line_coding->bit_rate )
  {
    baud_rate = line_coding->bit_rate;

    // must be the same freq as board_init()
    uint32_t freq;
    if (CLOCK_GetMux(kCLOCK_UartMux) == 0) /* PLL3 div6 80M */
    {
      freq = (CLOCK_GetPllFreq(kCLOCK_PllUsb1) / 6U) / (CLOCK_GetDiv(kCLOCK_UartDiv) + 1U);
    }
    else
    {
      freq = CLOCK_GetOscFreq() / (CLOCK_GetDiv(kCLOCK_UartDiv) + 1U);
    }

    LPUART_SetBaudRate(UART_DEV, baud_rate, freq);
  }
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
