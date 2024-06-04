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

#define CH32_UUID    ((volatile uint32_t *) 0x1FFFF7E8UL)

#define BOARD_PAGE_SIZE  0x800
#define FLASH_ADDR_PHY_BASE  0x08000000UL

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM DECLARATION
//--------------------------------------------------------------------+

// convert to zero-based address
#define ADDR_BASE0(_addr) ((_addr) & ~FLASH_ADDR_PHY_BASE)

// convert to absolute address
#define ADDR_ABS(_addr) ((_addr) | FLASH_ADDR_PHY_BASE)

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

  // double tap use backup register: enable PWR and BKP clock, and BKP write enable
  RCC_APB1PeriphClockCmd(RCC_APB1Periph_BKP | RCC_APB1Periph_PWR, ENABLE);
  PWR->CTLR |= PWR_CTLR_DBP;

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

void board_teardown(void) {
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
  uint32_t app_start_contents = *((volatile uint32_t const*) ADDR_ABS(BOARD_FLASH_APP_START));
  TUF2_LOG1_HEX(app_start_contents);
  // for ch32 after erased the flash value is 0xe339e339 (mentioned in RM) instead of 0xffffffff
  return app_start_contents != 0xe339e339;
}

// Jump to application code
void board_app_jump(void) {
  TUF2_LOG2("Jump to app\r\n");
  board_timer_stop();
  asm volatile("j __flash_boot_size");
}

uint8_t board_usb_get_serial(uint8_t serial_id[16]) {
  uint8_t const len = 12;
  uint32_t* serial_id32 = (uint32_t*) (uintptr_t) serial_id;

  serial_id32[0] = CH32_UUID[0];
  serial_id32[1] = CH32_UUID[1];
  serial_id32[2] = CH32_UUID[2];

  return len;
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
    USART_SendData(USART1, *bufc++);
    while (USART_GetFlagStatus(USART1, USART_FLAG_TXE) == RESET);
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
  // nothing to do
}

uint32_t board_flash_size(void) {
  return BOARD_FLASH_SIZE;
}

void board_flash_read(uint32_t addr, void* buffer, uint32_t len) {
  memcpy(buffer, (void*) addr, len);
}

void board_flash_flush(void) {
  // nothing to do
}

bool board_flash_write(uint32_t addr, void const* data, uint32_t len) {
  TUF2_ASSERT(len == 256);

  addr = ADDR_ABS(addr);

  FLASH_Unlock_Fast();

  FLASH_ErasePage_Fast(addr);
  FLASH_ProgramPage_Fast(addr, (uint32_t*) (uintptr_t ) data);

  FLASH_Lock_Fast();

  // verify contents
  if (memcmp((void*) addr, data, len) != 0) {
    TUF2_LOG1("Failed to write\r\n");
  }

  return true;
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
