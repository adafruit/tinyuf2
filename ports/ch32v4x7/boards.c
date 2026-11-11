// SPDX-FileCopyrightText: Copyright (c) 2026 Adafruit Industries
// SPDX-License-Identifier: MIT
#include "board_api.h"
#include "ch32v4x7_usb.h"
#ifndef BUILD_NO_TINYUSB
  #include "tusb.h"
#endif

void SysTick_Handler(void) __attribute__((interrupt, used));
void USBHS1_IRQHandler(void) __attribute__((interrupt, used));
void SW_Handler(void) __attribute__((interrupt, used));

/** @brief Enable the backup domain and initialize the activity LED. */
void board_init(void) {
  __disable_irq();
  RCC_PB1PeriphClockCmd(RCC_PB1Periph_BKP | RCC_PB1Periph_PWR, ENABLE);
  PWR->CTLR |= PWR_CTLR_DBP;
  RCC_PB2PeriphClockCmd(LED_CLOCK, ENABLE);
  GPIO_InitTypeDef led = {
    .GPIO_Pin   = LED_PIN,
    .GPIO_Mode  = GPIO_Mode_Out_PP,
    .GPIO_Speed = GPIO_Speed_High,
  };
  GPIO_Init(LED_PORT, &led);
  board_led_write(0);
  __enable_irq();
}

/** @brief Stop bootloader timers, USB activity and pending interrupts. */
void board_teardown(void) {
  __disable_irq();
  board_timer_stop();
  USBHS1D->INT_EN  = 0;
  USBHS1D->CONTROL = USBHS_UD_RST_SIE | USBHS_UD_RST_LINK;
  for (unsigned i = 0; i < 8; i++) {
    NVIC->IRER[i] = 0xffffffff;
    NVIC->IPRR[i] = 0xffffffff;
  }
}

/** @brief Start USBHS1 from the board crystal and enable its peripheral clock. */
void board_dfu_init(void) {
  // SystemInit starts the Metro's 25 MHz HSE and the 200 MHz core clock.
  // USBHS needs the crystal reference for reliable full-size packets.
  RCC->CTLR &= ~RCC_USBHSPLLON;
  RCC_USBHSPLLCLKConfig(RCC_USBHSPLLCLKSource_HSE);
  RCC_USBHSPLLReferConfig(RCC_USBHSPLLCKREFCLK_25M);
  RCC->CTLR |= RCC_USBHSPLLON;
  uint32_t timeout = 1000000;
  while (!(RCC->CTLR & RCC_USBHSPLLRDY) && --timeout) {}
  RCC_UTMI1cmd(ENABLE);
  RCC_HBPeriphClockCmd(RCC_HBPeriph_USBHS1, ENABLE);
}

#ifndef BUILD_APPLICATION
/** @brief Reset the MCU and wait for reset to take effect. */
void board_reset(void) {
  NVIC_SystemReset();
  while (1) {}
}

/** @brief Reset into the application only after all flash data is verified. */
void board_dfu_complete(void) {
  board_flash_flush();
  if (board_flash_ok()) {
    TINYUF2_DBL_TAP_REG = DBL_TAP_MAGIC_QUICK_BOOT;
    board_reset();
  }
}

/** @brief Accept a supported RISC-V jump at the application reset vector. */
bool board_app_valid(void) {
  const uint32_t first = *(volatile const uint32_t *)(FLASH_BASE + BOARD_FLASH_APP_START);
  // An erased WCH code-flash word reads E339E339. Accept a RISC-V JAL or
  // compressed jump at the application reset vector, not arbitrary data.
  return first != 0xe339e339u && first != 0xffffffffu && ((first & 0x7fu) == 0x6fu || (first & 0xe003u) == 0xa001u);
}

/** @brief Enter the software interrupt used for machine-mode application startup. */
void board_app_jump(void) {
  // The vendor startup enters user mode. Application reset code needs
  // machine mode to initialize its CSRs, as in WCH's V4x7 IAP example.
  NVIC_EnableIRQ(Software_IRQn);
  NVIC_SetPendingIRQ(Software_IRQn);
  __enable_irq();
  while (1) {}
}

/** @brief Jump to the configured application address in machine mode. */
void SW_Handler(void) {
  __disable_irq();
  NVIC_DisableIRQ(Software_IRQn);
  NVIC_ClearPendingIRQ(Software_IRQn);
  __asm volatile("fence.i\nli t0, %0\njr t0" ::"i"(BOARD_FLASH_APP_START) : "t0", "memory");
  __builtin_unreachable();
}

#endif

/** @brief Copy the MCU unique identifier into the USB serial buffer. */
uint8_t board_usb_get_serial(uint8_t serial_id[16]) {
  memcpy(serial_id, (const void *)0x1ffff7e8, 8);
  return 8;
}

/** @brief Drive the activity LED to the requested state. */
void board_led_write(uint32_t state) {
  GPIO_WriteBit(LED_PORT, LED_PIN, (state ? LED_STATE_ON : !LED_STATE_ON) ? Bit_SET : Bit_RESET);
}

/** @brief Ignore RGB updates because this bootloader uses only its activity LED. */
void board_rgb_write(const uint8_t rgb[]) {
  (void)rgb;
}

/** @brief Start the SysTick interval used for indicators and double-reset detection. */
void board_timer_start(uint32_t ms) {
  SysTick->CTLR = 0;
  SysTick->SR   = 0;
  SysTick->CNT  = 0;
  SysTick->CMP  = (SystemCoreClock / 1000) * ms - 1;
  NVIC_EnableIRQ(SysTick_IRQn);
  SysTick->CTLR = 0x0f;
}

/** @brief Stop SysTick and clear its pending interrupt. */
void board_timer_stop(void) {
  SysTick->CTLR = 0;
  NVIC_DisableIRQ(SysTick_IRQn);
  NVIC_ClearPendingIRQ(SysTick_IRQn);
}

/** @brief Acknowledge SysTick and advance the bootloader timer. */
void SysTick_Handler(void) {
  SysTick->SR = 0;
  board_timer_handler();
}

#ifndef BUILD_NO_TINYUSB
/** @brief Dispatch the device USB interrupt to TinyUSB. */
void USBHS1_IRQHandler(void) {
  tud_int_handler(0);
}
#endif

/** @brief Report no UART output because this port has no debug UART. */
int board_uart_write(const void *buf, int len) {
  (void)buf;
  (void)len;
  return 0;
}
