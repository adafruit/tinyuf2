/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2026 Ha Thach for Adafruit Industries
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

#include "ch32x035.h"
#include "board_api.h"

#ifndef BUILD_NO_TINYUSB
#include "tusb.h"
#endif

// flash is mapped at 0x00000000 and the fast-program page is 256 bytes
#define BOARD_PAGE_SIZE  256
#define CH32_UUID        ((volatile uint32_t *) 0x1FFFF7E8UL)

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

  LED_CLOCK_EN();

  GPIO_InitTypeDef GPIO_InitStructure = {
    .GPIO_Pin = LED_PIN,
    .GPIO_Mode = GPIO_Mode_Out_PP,
    .GPIO_Speed = GPIO_Speed_50MHz,
  };
  GPIO_Init(LED_PORT, &GPIO_InitStructure);

  #if CFG_TUSB_DEBUG || TUF2_LOG
  RCC_APB1PeriphClockCmd(RCC_APB1Periph_USART2, ENABLE);
  RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA, ENABLE);
  GPIO_InitTypeDef usart_init = {
    .GPIO_Pin = GPIO_Pin_2,
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
  USART_Init(USART2, &usart);
  USART_Cmd(USART2, ENABLE);
  #endif

  __enable_irq();
}

// called after board_init(), before the double-tap check
void board_init2(void) {
  // No backup registers on CH32X035: the double-tap flag lives in .noinit RAM,
  // which survives system resets but powers up as garbage. On a power-on reset
  // the flag cannot be trusted, so drop it (double tap uses the RESET key and
  // shows up as a pin reset with RAM retained).
  if ((RCC->RSTSCKR & RCC_PORRSTF) && !(RCC->RSTSCKR & RCC_SFTRSTF)) {
    _board_dfu_dbl_tap[0] = 0;
  }
  RCC->RSTSCKR |= RCC_RMVF; // consume the flags for the next boot
}

void board_teardown(void) {
  board_led_write(0);
}

void board_dfu_init(void) {
  __disable_irq();

  RCC_APB2PeriphClockCmd(RCC_APB2Periph_AFIO | RCC_APB2Periph_GPIOC, ENABLE);
  RCC_AHBPeriphClockCmd(RCC_AHBPeriph_USBFS, ENABLE);

  GPIO_InitTypeDef GPIO_InitStructure = {
    .GPIO_Pin = GPIO_Pin_16, // UDM
    .GPIO_Speed = GPIO_Speed_50MHz,
    .GPIO_Mode = GPIO_Mode_IN_FLOATING,
  };
  GPIO_Init(GPIOC, &GPIO_InitStructure);

  GPIO_InitStructure.GPIO_Pin = GPIO_Pin_17; // UDP
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IPU;
  GPIO_Init(GPIOC, &GPIO_InitStructure);

  // 3V3 transceiver, D+ 1.5k pull-up (AFIO_CTLR_UDP_PUE both bits), route USB
  // to PC16/PC17, following the SDK USBFS examples
  AFIO->CTLR = (AFIO->CTLR & ~(AFIO_CTLR_UDP_PUE | AFIO_CTLR_UDM_PUE)) |
               AFIO_CTLR_USB_PHY_V33 | AFIO_CTLR_UDP_PUE | AFIO_CTLR_USB_IOEN;

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
  uint32_t app_start_contents = *((volatile uint32_t const*) BOARD_FLASH_APP_START);
  TUF2_LOG1_HEX(app_start_contents);
  // erased flash pattern: 0xFFFFFFFF expected on x035, while the QingKe V2/V4
  // parts documented in their RMs read back 0xe339e339. Accept both until the
  // x035 RM value is confirmed on hardware.
  return app_start_contents != 0xFFFFFFFF && app_start_contents != 0xe339e339;
}

// Jump to application code, WCH IAP style: enter through a pending software
// interrupt. A plain branch into the app base traps on the app startup's
// csrw 0xbc0 with mcause=2 (verified with WCH-Link), while the interrupt entry
// path works — same mechanism as EVT/EXAM/IAP's SW_Handler.
void board_app_jump(void) {
  TUF2_LOG2("Jump to app\r\n");
  board_timer_stop();

  __disable_irq();

  // mask and un-pend every external interrupt: the app starts with all of them
  // disabled and re-enables what it uses
  for (uint32_t i = 0; i < 8; i++) {
    PFIC->IRER[i] = 0xFFFFFFFF;
    PFIC->IPRR[i] = 0xFFFFFFFF;
  }

  // reset and gate the USB IP, release the PHY pins
  RCC_AHBPeriphResetCmd(RCC_AHBPeriph_USBFS, ENABLE);
  RCC_AHBPeriphResetCmd(RCC_AHBPeriph_USBFS, DISABLE);
  RCC_AHBPeriphClockCmd(RCC_AHBPeriph_USBFS, DISABLE);
  AFIO->CTLR &= ~(AFIO_CTLR_UDP_PUE | AFIO_CTLR_UDM_PUE | AFIO_CTLR_USB_IOEN);

  __enable_irq();
  NVIC_EnableIRQ(Software_IRQn);
  NVIC_SetPendingIRQ(Software_IRQn);

  while (1) {} // SW_Handler takes it from here
}

void SW_Handler(void);

__attribute__((interrupt)) __attribute__((used))
void SW_Handler(void) {
  __disable_irq();
  // consume the software interrupt: without the HPE entry (WCH-Interrupt-fast,
  // gcc-wch only) the pending bit survives and re-fires inside the app
  NVIC_ClearPendingIRQ(Software_IRQn);
  NVIC_DisableIRQ(Software_IRQn);

  register uint32_t const app = BOARD_FLASH_APP_START;
  __asm volatile("jr %0" :: "r"(app));
  while (1) {}
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
  GPIO_WriteBit(LED_PORT, LED_PIN, state ? LED_STATE_ON : (1 - LED_STATE_ON));
}

void board_rgb_write(uint8_t const rgb[]) {
  (void) rgb;
}

//--------------------------------------------------------------------+
// Timer
//--------------------------------------------------------------------+
void board_timer_start(uint32_t ms) {
  SysTick_Config((SystemCoreClock / 1000) * ms);
}

void board_timer_stop(void) {
  SysTick->CTLR = 0;
  SysTick->SR = 0; // drop a pending tick: it would fire into the app's handler
}

__attribute__((interrupt)) __attribute__((used))
void SysTick_Handler(void) {
  SysTick->SR = 0;
  board_timer_handler();
}

int board_uart_write(void const* buf, int len) {
#if CFG_TUSB_DEBUG || TUF2_LOG
  const char* bufc = (const char*) buf;
  for (int i = 0; i < len; i++) {
    USART_SendData(USART2, *bufc++);
    while (USART_GetFlagStatus(USART2, USART_FLAG_TXE) == RESET) {}
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
  memcpy(buffer, (void*) (uintptr_t) addr, len);
}

void board_flash_flush(void) {
  // nothing to do
}

// flash is mapped at 0x00000000 for execution (alias) but the controller's ADDR
// register and the buffer-load stores take the 0x08000000-based address (FLASH_BASE)
#define FLASH_ADDR_ABS(_addr) ((_addr) | 0x08000000UL)

// erase+program one 256-byte fast page with IRQs masked: the bus stalls while
// the controller is busy, same as the SDK MSC example
static bool flash_write_page(uint32_t addr, void const* data) {
  uint32_t const abs = FLASH_ADDR_ABS(addr);

  FLASH_Unlock_Fast();

  FLASH_ErasePage_Fast(abs);
  FLASH_BufReset();
  uint32_t const* data32 = (uint32_t const*) data;
  for (uint32_t i = 0; i < BOARD_PAGE_SIZE / 4; i++) {
    FLASH_BufLoad(abs + 4 * i, data32[i]);
  }
  FLASH_ProgramPage_Fast(abs);

  FLASH_Lock_Fast();
  return memcmp((void*) (uintptr_t) addr, data, BOARD_PAGE_SIZE) == 0;
}

bool board_flash_write(uint32_t addr, void const* data, uint32_t len) {
  TUF2_ASSERT(len == BOARD_PAGE_SIZE);

  // reject pages outside the application region: uf2_write_block() passes the
  // file's targetAddr through unfiltered, so a family-matching UF2 linked at
  // address 0 would otherwise erase the bootloader itself (the subtraction
  // form cannot wrap the way addr + len would on a huge targetAddr)
  if (len != BOARD_PAGE_SIZE || addr < BOARD_FLASH_APP_START ||
      addr > BOARD_FLASH_SIZE - len ||
      (addr & (BOARD_PAGE_SIZE - 1)) != 0) {
    TUF2_LOG1("Rejected flash write at 0x%08lX\r\n", addr);
    return false;
  }

  // note: reading mstatus (csrr 0x300) raises an illegal-instruction trap on
  // QingKe V4C (hardware-verified via WCH-Link, mcause=2), so the IRQ state is
  // not saved/restored around the flash op; interrupts are on in DFU mode
  __disable_irq();
  bool const ok = flash_write_page(addr, data);
  __enable_irq();

  if (!ok) {
    TUF2_LOG1("Failed to write\r\n");
  }
  return ok;
}

void board_flash_erase_app(void) {
  // no mstatus save/restore: reading mstatus traps on QingKe V4C (see board_flash_write)
  __disable_irq();

  FLASH_Unlock_Fast();
  for (uint32_t addr = BOARD_FLASH_APP_START; addr < BOARD_FLASH_SIZE; addr += BOARD_PAGE_SIZE) {
    FLASH_ErasePage_Fast(FLASH_ADDR_ABS(addr));
  }
  FLASH_Lock_Fast();

  __enable_irq();
}

bool board_flash_protect_bootloader(bool protect) {
  // TODO implement later
  (void) protect;
  return false;
}

#ifdef TINYUF2_SELF_UPDATE
void board_self_update(const uint8_t* bootloader_bin, uint32_t bootloader_len) {
  (void) bootloader_bin;
  (void) bootloader_len;
}
#endif

//--------------------------------------------------------------------+
// USB Interrupt Handler
//--------------------------------------------------------------------+

#ifndef BUILD_NO_TINYUSB
__attribute__((interrupt)) __attribute__((used))
void USBFS_IRQHandler(void) {
  tud_int_handler(0);
}

__attribute__((interrupt)) __attribute__((used))
void USBFSWakeUp_IRQHandler(void) {
  tud_int_handler(0);
}
#endif
