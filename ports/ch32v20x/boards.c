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

#include "ch32v20x.h"
#include "board_api.h"

#ifndef BUILD_NO_TINYUSB
#include "tusb.h"
#endif

// symbol from linker
extern uint32_t __flash_size[];
extern uint32_t __flash_boot_size[];

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM DECLARATION
//--------------------------------------------------------------------+

uint32_t SysTick_Config(uint32_t ticks) {
  NVIC_EnableIRQ(SysTicK_IRQn);
  SysTick->CTLR = 0;
  SysTick->SR = 0;
  SysTick->CNT = 0;
  SysTick->CMP = ticks - 1;
  SysTick->CTLR = 0xF;
  return 0;
}

void board_init(void) {
  __disable_irq();

  RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA, ENABLE);

  GPIO_InitTypeDef GPIO_InitStructure = {
      .GPIO_Pin = LED_PIN,
      .GPIO_Mode = GPIO_Mode_Out_OD,
      .GPIO_Speed = GPIO_Speed_50MHz,
  };
  GPIO_Init(LED_PORT, &GPIO_InitStructure);

  #if CFG_TUSB_DEBUG || TUF2_LOG
  RCC_APB2PeriphClockCmd(RCC_APB2Periph_USART1, ENABLE);
  GPIO_InitTypeDef usart_init = {
      .GPIO_Pin = GPIO_Pin_9,
      .GPIO_Speed = GPIO_Speed_50MHz,
      .GPIO_Mode = GPIO_Mode_AF_PP,
  };
  GPIO_Init(GPIOA, &usart_init);

  USART_InitTypeDef usart = {
      .USART_BaudRate = 115200,
      .USART_WordLength = USART_WordLength_8b,
      .USART_StopBits = USART_StopBits_1,
      .USART_Parity = USART_Parity_No,
      .USART_Mode = USART_Mode_Tx,
      .USART_HardwareFlowControl = USART_HardwareFlowControl_None,
  };
  USART_Init(USART1, &usart);
  USART_Cmd(USART1, ENABLE);
  #endif

  __enable_irq();
}

void board_dfu_init(void) {
  __disable_irq();

  uint8_t usb_div;
  switch (SystemCoreClock) {
    case 48000000: usb_div = RCC_USBCLKSource_PLLCLK_Div1; break;
    case 96000000: usb_div = RCC_USBCLKSource_PLLCLK_Div2; break;
    case 144000000: usb_div = RCC_USBCLKSource_PLLCLK_Div3; break;
    default: TU_ASSERT(0,); break;
  }
  RCC_USBCLKConfig(usb_div);

#if CFG_TUD_WCH_USBIP_USBFS
  RCC_AHBPeriphClockCmd(RCC_AHBPeriph_OTG_FS, ENABLE); // USB FS
#endif

#if CFG_TUD_WCH_USBIP_FSDEV
  RCC_APB1PeriphClockCmd(RCC_APB1Periph_USB, ENABLE);  // FSDEV
#endif

  __enable_irq();
}

void board_reset(void) {
   NVIC_SystemReset();
}

void board_dfu_complete(void) {
  // Mostly reset
 NVIC_SystemReset();
}

bool board_app_valid(void) {
  return false;
}

void board_app_jump(void) {
  // Jump to application code
}

uint8_t board_usb_get_serial(uint8_t serial_id[16]) {
  (void) serial_id;
  return 0;
}

//--------------------------------------------------------------------+
// LED pattern
//--------------------------------------------------------------------+

void board_led_write(uint32_t state) {
  GPIO_WriteBit(LED_PORT, LED_PIN, state ? LED_STATE_ON : (1-LED_STATE_ON));
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
  SysTick->CTLR = 0;
}

__attribute__((interrupt)) __attribute__((used))
void SysTick_Handler(void) {
  SysTick->SR = 0;
  board_timer_handler();
}

int board_uart_write(void const* buf, int len) {
#if CFG_TUSB_DEBUG || TUF2_LOG
  const char *bufc = (const char *) buf;
  for (int i = 0; i < len; i++) {
    while (USART_GetFlagStatus(USART1, USART_FLAG_TC) == RESET);
    USART_SendData(USART1, *bufc++);
  }
  return len;
#else
  (void) buf;
  (void) len;
  return 0;
#endif
}

//--------------------------------------------------------------------+
// Flash
//--------------------------------------------------------------------+
void board_flash_init(void) {

}

uint32_t board_flash_size(void) {
  return (uint32_t) __flash_size;
}

void board_flash_read(uint32_t addr, void* buffer, uint32_t len) {
  (void) addr;
  (void) buffer;
  (void) len;
}

void board_flash_flush(void) {
}

void board_flash_write(uint32_t addr, void const* data, uint32_t len) {
  (void) addr;
  (void) data;
  (void) len;
}

void board_flash_erase_app(void) {
  // TODO implement later
}

bool board_flash_protect_bootloader(bool protect) {
  // TODO implement later
  (void) protect;
  return false;
}

#ifdef TINYUF2_SELF_UPDATE
void board_self_update(const uint8_t * bootloader_bin, uint32_t bootloader_len) {
  (void) bootloader_bin;
  (void) bootloader_len;
}
#endif

//--------------------------------------------------------------------+
// USB Interrupt Handler
//--------------------------------------------------------------------+

#ifndef BUILD_NO_TINYUSB
// USBFS
__attribute__((interrupt)) __attribute__((used))
void USBFS_IRQHandler(void) {
  #if CFG_TUD_WCH_USBIP_USBFS
  tud_int_handler(0);
  #endif
}

__attribute__((interrupt)) __attribute__((used))
void USBFSWakeUp_IRQHandler(void) {
  #if CFG_TUD_WCH_USBIP_USBFS
  tud_int_handler(0);
  #endif
}

// USBD (fsdev)
__attribute__((interrupt)) __attribute__((used))
void USB_LP_CAN1_RX0_IRQHandler(void) {
  #if CFG_TUD_WCH_USBIP_FSDEV
  tud_int_handler(0);
  #endif
}

__attribute__((interrupt)) __attribute__((used))
void USB_HP_CAN1_TX_IRQHandler(void) {
  #if CFG_TUD_WCH_USBIP_FSDEV
  tud_int_handler(0);
  #endif
}

__attribute__((interrupt)) __attribute__((used))
void USBWakeUp_IRQHandler(void) {
  #if CFG_TUD_WCH_USBIP_FSDEV
  tud_int_handler(0);
  #endif
}
#endif
