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

// optional API, not included in board_api.h
int board_uart_read(uint8_t* buf, int len);


// TODO ESP32 pindef for Metro M7 1011, move to board.h later
#define ESP_GPIO0_PINMUX  IOMUXC_GPIO_SD_05_GPIO2_IO05
#define ESP_GPIO0_PORT    GPIO2
#define ESP_GPIO0_PIN     5

#define ESP_RESET_PINMUX  IOMUXC_GPIO_AD_07_GPIOMUX_IO21
#define ESP_RESET_PORT    GPIO1
#define ESP_RESET_PIN     21

static volatile uint32_t _timer_count = 0;
static uint32_t baud_rate = 115200;
static uint8_t serial_buf[512];

int main(void)
{
  board_init();
  board_uart_init(115200);

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
    uint32_t count;

    // USB -> UART
    while( tud_cdc_available() )
    {
      count = tud_cdc_read(serial_buf, sizeof(serial_buf));
      board_uart_write(serial_buf, count);
    }

    // UART -> USB
    count = board_uart_read(serial_buf, sizeof(serial_buf));
    if (count)
    {
      tud_cdc_write(serial_buf, count);
      tud_cdc_write_flush();
    }

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

// Invoked when cdc when line state changed e.g connected/disconnected
void tud_cdc_line_state_cb(uint8_t itf, bool dtr, bool rts)
{
  (void) itf;
  (void) dtr;
  (void) rts;

  // TODO ESP tool does use DTR and RTS, maybe we could have some usage
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
