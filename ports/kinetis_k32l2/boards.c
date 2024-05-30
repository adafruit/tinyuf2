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

#include "board_api.h"
#include "fsl_rtc.h"
#include "fsl_gpio.h"
#include "fsl_port.h"
#include "fsl_clock.h"
#include "fsl_lpuart.h"
#include "clock_config.h"
#include "tusb.h"

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM DECLARATION
//--------------------------------------------------------------------+
void board_init(void)
{
  BOARD_BootClockRUN();
  CLOCK_EnableClock(kCLOCK_Rtc0);

  SystemCoreClockUpdate();

  board_timer_stop();

#ifdef LED_PIN
  CLOCK_EnableClock(LED_CLK_PORT);
  gpio_pin_config_t led_config = { kGPIO_DigitalOutput, 0 };
  GPIO_PinInit(LED_GPIO, LED_PIN, &led_config);
  PORT_SetPinMux(LED_PORT, LED_PIN, kPORT_MuxAsGpio);
#endif

#ifdef KUIIC_RGB_LED
  kuiic_rgb_init();
#endif

#ifdef BUTTON_PIN
  CLOCK_EnableClock(BUTTON_CLK_PORT);
  gpio_pin_config_t button_config = { kGPIO_DigitalInput, 0 };
  GPIO_PinInit(BUTTON_GPIO, BUTTON_PIN, &button_config);
  const port_pin_config_t BUTTON_CFG = {
    kPORT_PullUp,
    kPORT_FastSlewRate,
    kPORT_PassiveFilterDisable,
    kPORT_LowDriveStrength,
    kPORT_MuxAsGpio
  };
  PORT_SetPinConfig(BUTTON_PORT, BUTTON_PIN, &BUTTON_CFG);
#endif

#if defined(UART_DEV) && CFG_TUSB_DEBUG
  UART_SET_CLOCK;
  CLOCK_EnableClock(UART_CLK_PORT);
  PORT_SetPinMux(UART_PIN_PORT, UART_RX_PIN, UART_RX_MUX);
  PORT_SetPinMux(UART_PIN_PORT, UART_TX_PIN, UART_TX_MUX);
#ifdef UART_SOPT_INIT
  UART_SOPT_INIT;
#endif
  lpuart_config_t uart_config;
  LPUART_GetDefaultConfig(&uart_config);
  uart_config.baudRate_Bps = BOARD_UART_BAUDRATE;
  uart_config.enableTx = true;
  uart_config.enableRx = true;
  LPUART_Init(UART_DEV, &uart_config, CLOCK_GetFreq(kCLOCK_McgIrc48MClk));
  TU_LOG2("UART Configured\r\n");
#endif

}

void board_usb_init(void)
{
  CLOCK_EnableUsbfs0Clock(kCLOCK_UsbSrcIrc48M, 48000000U);
}

void board_dfu_init(void)
{
  board_usb_init();
}

void board_reset(void)
{
  NVIC_SystemReset();
}

void board_dfu_complete(void)
{
  // Mostly reset
  NVIC_SystemReset();
}

bool board_app_valid(void)
{
  volatile uint32_t const * app_vector = (volatile uint32_t const*) BOARD_FLASH_APP_START;

  // 1st word is stack pointer (should be in SRAM region)

  // 2nd word is App entry point (reset)
  if (app_vector[1] < BOARD_FLASH_APP_START || app_vector[1] > BOARD_FLASH_APP_START + BOARD_FLASH_SIZE) {
    return false;
  }

  return true;
}

void board_app_jump(void)
{
  // Create the function call to the user application.
  // Static variables are needed since changed the stack pointer out from under the compiler
  // we need to ensure the values we are using are not stored on the previous stack
  static uint32_t stack_pointer;
  static uint32_t app_entry;

  // Clear RTC registers used for double tap
  RTC_Reset(RTC);

  uint32_t const * app_vector = (uint32_t const*) BOARD_FLASH_APP_START;
  stack_pointer = app_vector[0];
  app_entry = app_vector[1];

  // TODO protect bootloader region

  /* switch exception handlers to the application */
  SCB->VTOR = (uint32_t) BOARD_FLASH_APP_START;

  // Set stack pointer
  __set_MSP(stack_pointer);
  __set_PSP(stack_pointer);

  // Jump to Application Entry
  asm("bx %0" ::"r"(app_entry));
}

uint8_t board_usb_get_serial(uint8_t serial_id[16])
{
  uint32_t wr = SIM->UIDL;
  serial_id[0] = wr & 0xFF;
  wr >>= 8;
  serial_id[1] = wr & 0xFF;
  wr >>= 8;
  serial_id[2] = wr & 0xFF;
  wr >>= 8;
  serial_id[3] = wr & 0xFF;
  wr >>= SIM->UIDML;
  serial_id[4] = wr & 0xFF;
  wr >>= 8;
  serial_id[5] = wr & 0xFF;
  wr >>= 8;
  serial_id[6] = wr & 0xFF;
  wr >>= 8;
  serial_id[7] = wr & 0xFF;
  wr >>= SIM->UIDMH;
  serial_id[8] = wr & 0xFF;
  wr >>= 8;
  serial_id[9] = wr & 0xFF;
  return 10;
}

//--------------------------------------------------------------------+
// LED pattern
//--------------------------------------------------------------------+

void board_led_write(uint32_t state)
{
  (void) state;
#ifdef LED_PIN
  GPIO_PinWrite(LED_GPIO, LED_PIN, ((state)? LED_STATE_ON : (1-LED_STATE_ON)));
#endif
}

void board_rgb_write(uint8_t const rgb[])
{
  (void) rgb;
#ifdef KUIIC_RGB_LED
  kuiic_rgb_write(rgb);
#endif
}

//--------------------------------------------------------------------+
// Timer
//--------------------------------------------------------------------+

void board_timer_start(uint32_t ms)
{
  SysTick_Config( (SystemCoreClock/1000) * ms );
}

void board_timer_stop(void)
{
  //SysTick->CTRL = 0;
  SysTick->CTRL &= ~SysTick_CTRL_ENABLE_Msk;
}

void SysTick_Handler (void)
{
  board_timer_handler();
#ifdef KUIIC_RGB_LED
  kuiic_rgb_tick();
#endif
}


int board_uart_write(void const * buf, int len)
{
#ifdef UART_DEV
  uint8_t const* buf8 = (uint8_t const*) buf;
  int count = 0;

  while(count < len)
  {
    if (LPUART_GetStatusFlags(UART_DEV) & kLPUART_TxDataRegEmptyFlag)
    {
      LPUART_WriteByte(UART_DEV, *buf8++);
      count++;
    }
  }

  return len;

#else

  (void) buf; (void) len;
  return 0;
#endif
}

// optional API, not included in board_api.h
int board_uart_read(uint8_t* buf, int len)
{
  (void) buf; (void) len;
  return 0;
}

//--------------------------------------------------------------------+
// USB Interrupt Handler
//--------------------------------------------------------------------+
#ifndef BUILD_NO_TINYUSB

void USB0_IRQHandler(void)
{
  tud_int_handler(0);
}

#endif
