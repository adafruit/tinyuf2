/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2025 Brent Kowal, Analog Devices, Inc
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

#ifndef BUILD_NO_TINYUSB
#include "tusb.h"
#endif

// MAX MSDK Includes
#include "flc.h"
#include "gpio.h"
#include "icc.h"
#include "mxc_sys.h"
#include "mxc_device.h"
#include "uart.h"

//Get the register base from UART number
static mxc_uart_regs_t *ConsoleUart = MXC_UART_GET_UART(UART_NUM);

void board_init(void) {
  mxc_gpio_cfg_t gpioConfig;

  // LED
  gpioConfig.drvstr = MXC_GPIO_DRVSTR_0;
  gpioConfig.func =   MXC_GPIO_FUNC_OUT;
  gpioConfig.mask =   LED_PIN;
  gpioConfig.pad =    MXC_GPIO_PAD_NONE;
  gpioConfig.port =   LED_PORT;
  gpioConfig.vssel =  LED_VDDIO;
  MXC_GPIO_Config(&gpioConfig);
  board_led_write(false);

  // UART
#if MAX_PERIPH_ID == 14
  MXC_UART_Init(ConsoleUart, BOARD_UART_BAUDRATE, UART_MAP);
#elif MAX_PERIPH_ID == 18 || MAX_PERIPH_ID == 87
  MXC_UART_Init(ConsoleUart, BOARD_UART_BAUDRATE, MXC_UART_IBRO_CLK);
  #if MAX_PERIPH_ID == 87
  UART_PORT->vssel |= UART_VDDIO_BITS; //Set necessary bits to 3.3V
  #endif
#endif

}

void board_teardown(void) {
  //Nothing to do
}

void board_dfu_init(void) {
  // Init USB for DFU
#if defined(MAX32650)
  // Startup the HIRC96M clock if it's not on already
  if (!(MXC_GCR->clk_ctrl & MXC_F_GCR_CLK_CTRL_HIRC96_EN)) {
    MXC_GCR->clk_ctrl |= MXC_F_GCR_CLK_CTRL_HIRC96_EN;
    MXC_SYS_Clock_Timeout(MXC_F_GCR_CLK_CTRL_HIRC96_RDY);
  }
  MXC_SYS_ClockEnable(MXC_SYS_PERIPH_CLOCK_USB);
  MXC_SYS_Reset_Periph(MXC_SYS_RESET_USB);

#elif defined(MAX32665) || defined(MAX32666)
  // Startup the HIRC96M clock if it's not on already
  if (!(MXC_GCR->clkcn & MXC_F_GCR_CLKCN_HIRC96M_EN)) {
    MXC_GCR->clkcn |= MXC_F_GCR_CLKCN_HIRC96M_EN;
  }
  MXC_SYS_ClockEnable(MXC_SYS_PERIPH_CLOCK_USB);
  MXC_SYS_Reset_Periph(MXC_SYS_RESET_USB);

#elif defined(MAX32690)
  MXC_SYS_ClockSourceEnable(MXC_SYS_CLOCK_IPO);
  MXC_MCR->ldoctrl |= MXC_F_MCR_LDOCTRL_0P9EN;
  MXC_SYS_ClockEnable(MXC_SYS_PERIPH_CLOCK_USB);
  MXC_SYS_Reset_Periph(MXC_SYS_RESET0_USB);

#  elif  defined(MAX78002)
  MXC_MCR->ldoctrl |= MXC_F_MCR_LDOCTRL_0P9EN;
  MXC_SYS_ClockEnable(MXC_SYS_PERIPH_CLOCK_USB);
#else
  #error "Unsupported MAXIM MCU for board_dfu_init"
#endif
}

void board_reset(void) {
  NVIC_SystemReset();
}

void board_dfu_complete(void) {
  // Mostly reset
  NVIC_SystemReset();
}

bool board_app_valid(void) {
  volatile uint32_t const * app_vector = (volatile uint32_t const*) BOARD_FLASH_APP_START;

  // 1st word is stack pointer (should be in SRAM region)
  if ((app_vector[0] < MXC_SRAM_MEM_BASE) ||
      (app_vector[0] >= MXC_SRAM_MEM_BASE + MXC_SRAM_MEM_SIZE)) {
    return false;
  }
  // 2nd word is App entry point (reset)
  if ((app_vector[1] < BOARD_FLASH_APP_START) ||
      (app_vector[1] > BOARD_FLASH_ADDR_LAST)) {
    return false;
  }

  return true;
}

void board_app_jump(void) {
  // Create the function call to the user application.
  // Static variables are needed since changed the stack pointer out from under the compiler
  // we need to ensure the values we are using are not stored on the previous stack
  static uint32_t stack_pointer;
  static uint32_t app_entry;

  uint32_t const * app_vector = (uint32_t const*) BOARD_FLASH_APP_START;
  stack_pointer = app_vector[0];
  app_entry = app_vector[1];

  // Do a soft reset to reset all the peripherals to POR state. Does not impact
  // CPU state, RAM retention or the Always-On domain.  This should make the
  // application think it was as close to POR as possible
#if defined(MAX32665) || defined(MAX32666)
  MXC_GCR->rstr0 |= MXC_F_GCR_RSTR0_SRST;
#elif defined(MAX32650) || defined(MAX32690) || defined(MAX78002)
  MXC_GCR->rst0 |= MXC_F_GCR_RST0_SOFT;
#else
  #error "Unsupported MAXIM MCU for board_app_jump"
#endif

  // switch exception handlers to the application
  SCB->VTOR = (uint32_t) BOARD_FLASH_APP_START;

  // Set stack pointer
  __set_MSP(stack_pointer);
  __set_PSP(stack_pointer);

  // Jump to Application Entry
  asm("bx %0" ::"r"(app_entry));
}

uint8_t board_usb_get_serial(uint8_t serial_id[16]) {
#if defined(MAX32650)
  // USN is 13 bytes on this device
  MXC_SYS_GetUSN(serial_id, 13);
  return 13;
#else
  uint8_t hw_id[MXC_SYS_USN_CHECKSUM_LEN]; //USN Buffer
  uint8_t act_len;
  MXC_SYS_GetUSN(hw_id, NULL); // 2nd parameter is optional checksum buffer

  act_len = TUF2_MIN(16, MXC_SYS_USN_CHECKSUM_LEN);
  memcpy(serial_id, hw_id, act_len);
  return act_len;
#endif
}

//--------------------------------------------------------------------+
// LED pattern
//--------------------------------------------------------------------+

void board_led_write(uint32_t state) {
#if LED_STATE_ON
  state = !state;
#endif
  if (state) {
    MXC_GPIO_OutClr(LED_PORT, LED_PIN);
  } else {
    MXC_GPIO_OutSet(LED_PORT, LED_PIN);
  }
}

void board_rgb_write(uint8_t const rgb[]) {
  (void) rgb;
}

//--------------------------------------------------------------------+
// Timer
//--------------------------------------------------------------------+

void board_timer_start(uint32_t ms) {
  SysTick_Config( (SystemCoreClock/1000) * ms );
}

void board_timer_stop(void) {
  SysTick->CTRL &= ~SysTick_CTRL_ENABLE_Msk;
}

void SysTick_Handler(void) {
  board_timer_handler();
}

int board_uart_write(void const* buf, int len) {
  int act_len = 0;
  const uint8_t *ch_ptr = (const uint8_t *) buf;
  while (act_len < len) {
    MXC_UART_WriteCharacter(ConsoleUart, *ch_ptr++);
    act_len++;
  }
  return len;
}


//--------------------------------------------------------------------+
// USB Interrupt Handler
//--------------------------------------------------------------------+

#ifndef BUILD_NO_TINYUSB
// Forward USB interrupt events to TinyUSB IRQ Handler
void USB_IRQHandler(void) {
  tud_int_handler(0);
}
#endif

// Required by __libc_init_array in startup code if we are compiling using
// -nostdlib/-nostartfiles.
__attribute__((used)) void _init(void) {
}
