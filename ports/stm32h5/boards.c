/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2018 Ha Thach for Adafruit Industries
 * Copyright (c) 2023 HiFiPhile
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
#include "stm32h5xx_hal.h"

#ifndef BUILD_NO_TINYUSB
#include "tusb.h"
#endif

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM DECLARATION
//--------------------------------------------------------------------+

#define STM32_UUID    ((volatile uint32_t *) UID_BASE)


//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM
//--------------------------------------------------------------------+
#if defined(UART_DEV) && CFG_TUSB_DEBUG
  #define USE_UART 1
#else
  #define USE_UART 0
#endif

#if USE_UART
UART_HandleTypeDef UartHandle = {
  .Instance        = UART_DEV,
  .Init.BaudRate   = BOARD_UART_BAUDRATE,
  .Init.WordLength = UART_WORDLENGTH_8B,
  .Init.StopBits   = UART_STOPBITS_1,
  .Init.Parity     = UART_PARITY_NONE,
  .Init.HwFlowCtl  = UART_HWCONTROL_NONE,
  .Init.Mode       = UART_MODE_TX_RX,
  .Init.OverSampling = UART_OVERSAMPLING_16,
  .AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT
};
#endif

void board_init(void)
{
#ifdef BUILD_APPLICATION
  // system_stm32h5xx.c: SystemInit() will reset vector table, set it here if we are building application
  SCB->VTOR = (uint32_t) BOARD_FLASH_APP_START;
#endif

  HAL_Init();           // required for HAL_RCC_Osc TODO check with freeRTOS
  SystemClock_Config(); // implemented in board.h
  SystemCoreClockUpdate();

  // Enable All GPIOs clocks
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOH_CLK_ENABLE();

  #ifdef __HAL_RCC_GPIOE_CLK_ENABLE
  __HAL_RCC_GPIOE_CLK_ENABLE();
  #endif

  #ifdef __HAL_RCC_GPIOG_CLK_ENABLE
  __HAL_RCC_GPIOG_CLK_ENABLE();
  #endif

  #ifdef __HAL_RCC_GPIOI_CLK_ENABLE
  __HAL_RCC_GPIOI_CLK_ENABLE();
  #endif

  GPIO_InitTypeDef GPIO_InitStruct;

  // LED
  GPIO_InitStruct.Pin = LED_PIN;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(LED_PORT, &GPIO_InitStruct);

  board_led_write(false);

  // Button
  GPIO_InitStruct.Pin = BUTTON_PIN;
  GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = BUTTON_STATE_ACTIVE ? GPIO_PULLDOWN : GPIO_PULLUP;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(BUTTON_PORT, &GPIO_InitStruct);

  #if USE_UART
  UART_CLOCK_ENABLE();
  // UART
  GPIO_InitStruct.Pin = UART_TX_PIN | UART_RX_PIN;
  GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  GPIO_InitStruct.Alternate = UART_GPIO_AF;
  HAL_GPIO_Init(UART_GPIO_PORT, &GPIO_InitStruct);
  HAL_UART_Init(&UartHandle);
  #endif
}

void board_dfu_init(void)
{
  GPIO_InitTypeDef  GPIO_InitStruct;

  /* Configure DM DP Pins */
  GPIO_InitStruct.Pin = (GPIO_PIN_11 | GPIO_PIN_12);
  GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /* Enable VDDUSB */
  #if defined (PWR_USBSCR_USB33DEN)
  HAL_PWREx_EnableVddUSB();
  #endif

  // Enable USB OTG clock
  __HAL_RCC_USB_CLK_ENABLE();
}

void board_reset(void) {
  NVIC_SystemReset();
}

void board_dfu_complete(void) {
  NVIC_SystemReset();
}

bool board_app_valid(void)
{
  volatile uint32_t const * app_vector = (volatile uint32_t const*) BOARD_FLASH_APP_START;
  uint32_t sp = app_vector[0];
  uint32_t app_entry = app_vector[1];

  TUF2_LOG1_HEX(sp);
  TUF2_LOG1_HEX(app_entry);

  // 1st word is stack pointer (must be in SRAM region)
  if ((sp & 0xff000003) != 0x20000000) return false;

  // 2nd word is App entry point (reset)
  if (app_entry < BOARD_FLASH_APP_START || app_entry > BOARD_FLASH_APP_START + BOARD_FLASH_SIZE) {
    return false;
  }

  return true;
}

void board_teardown(void) {
#ifdef BUTTON_PIN
  HAL_GPIO_DeInit(BUTTON_PORT, BUTTON_PIN);
#endif

#ifdef LED_PIN
  HAL_GPIO_DeInit(LED_PORT, LED_PIN);
#endif

#if NEOPIXEL_NUMBER
  HAL_GPIO_DeInit(NEOPIXEL_PORT, NEOPIXEL_PIN);
#endif

#if USE_UART
  HAL_UART_DeInit(&UartHandle);
  HAL_GPIO_DeInit(UART_GPIO_PORT, UART_TX_PIN | UART_RX_PIN);
  UART_CLOCK_DISABLE();
#endif

#if defined (PWR_USBSCR_USB33DEN)
  HAL_PWREx_DisableVddUSB();
#endif
  __HAL_RCC_USB_CLK_DISABLE();
  HAL_GPIO_DeInit(GPIOA, GPIO_PIN_11 | GPIO_PIN_12); // USB

  __HAL_RCC_GPIOA_CLK_DISABLE();
  __HAL_RCC_GPIOB_CLK_DISABLE();
  __HAL_RCC_GPIOC_CLK_DISABLE();
  __HAL_RCC_GPIOD_CLK_DISABLE();
  __HAL_RCC_GPIOH_CLK_DISABLE();

#ifdef __HAL_RCC_GPIOE_CLK_DISABLE
  __HAL_RCC_GPIOE_CLK_DISABLE();
#endif

#ifdef __HAL_RCC_GPIOG_CLK_DISABLE
  __HAL_RCC_GPIOG_CLK_DISABLE();
#endif

#ifdef __HAL_RCC_GPIOI_CLK_DISABLE
  __HAL_RCC_GPIOI_CLK_DISABLE();
#endif

  HAL_RCC_DeInit();
  HAL_DeInit();

  SysTick->CTRL = 0;
  SysTick->LOAD = 0;
  SysTick->VAL = 0;
}

void board_app_jump(void)
{
  volatile uint32_t const * app_vector = (volatile uint32_t const*) BOARD_FLASH_APP_START;
  uint32_t sp = app_vector[0];
  uint32_t app_entry = app_vector[1];

  // Disable all Interrupts
  for (uint8_t i=0; i<sizeof(NVIC->ICER)/sizeof(NVIC->ICER[0]); i++) {
    NVIC->ICER[i] = 0xFFFFFFFFu;
  }

  /* switch exception handlers to the application */
  SCB->VTOR = (uint32_t) BOARD_FLASH_APP_START;

  // Set stack pointer
  __set_MSP(sp);
  __set_PSP(sp);

  // Jump to Application Entry
  asm("bx %0" ::"r"(app_entry));
}

uint8_t board_usb_get_serial(uint8_t serial_id[16])
{
  uint8_t const len = 12;
  uint32_t* serial_id32 = (uint32_t*) (uintptr_t) serial_id;

  serial_id32[0] = STM32_UUID[0];
  serial_id32[1] = STM32_UUID[1];
  serial_id32[2] = STM32_UUID[2];

  return len;
}

//--------------------------------------------------------------------+
// LED pattern
//--------------------------------------------------------------------+

void board_led_write(uint32_t state)
{
  HAL_GPIO_WritePin(LED_PORT, LED_PIN, state ? LED_STATE_ON : (1-LED_STATE_ON));
}

#if NEOPIXEL_NUMBER
#define MAGIC_800_INT   900000  // ~1.11 us -> 1.2  field
#define MAGIC_800_T0H  2800000  // ~0.36 us -> 0.44 field
#define MAGIC_800_T1H  1350000  // ~0.74 us -> 0.84 field

static inline uint8_t apply_percentage(uint8_t brightness)
{
  return (uint8_t) ((brightness*NEOPIXEL_BRIGHTNESS) >> 8);
}

void board_rgb_write(uint8_t const rgb[]) {
  // assumes 800_000Hz frequency
  // Theoretical values here are 800_000 -> 1.25us, 2500000->0.4us,
  // 1250000->0.8us
  uint32_t const sys_freq = HAL_RCC_GetSysClockFreq();
  uint32_t const interval = sys_freq / MAGIC_800_INT;
  uint32_t const t0 = sys_freq / MAGIC_800_T0H;
  uint32_t const t1 = sys_freq / MAGIC_800_T1H;

  // neopixel color order is GRB
  uint8_t const colors[3] = {apply_percentage(rgb[1]), apply_percentage(rgb[0]),
                             apply_percentage(rgb[2])};

  __disable_irq();
  uint32_t start;
  uint32_t cyc;

  // Enable DWT in debug core. Usable when interrupts disabled, as opposed to
  // Systick->VAL
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
  DWT->CYCCNT = 0;

  for (uint32_t i = 0; i < NEOPIXEL_NUMBER; i++) {
    uint8_t const *color_pointer = colors;
    uint8_t const *const color_pointer_end = color_pointer + 3;
    uint8_t color = *color_pointer++;
    uint8_t color_mask = 0x80;

    while (true) {
      cyc = (color & color_mask) ? t1 : t0;
      start = DWT->CYCCNT;

      HAL_GPIO_WritePin(NEOPIXEL_PORT, NEOPIXEL_PIN, 1);
      while ((DWT->CYCCNT - start) < cyc)
        ;

      HAL_GPIO_WritePin(NEOPIXEL_PORT, NEOPIXEL_PIN, 0);
      while ((DWT->CYCCNT - start) < interval)
        ;

      if (!(color_mask >>= 1)) {
        if (color_pointer >= color_pointer_end) {
          break;
        }
        color = *color_pointer++;
        color_mask = 0x80;
      }
    }
  }

  __enable_irq();
}

#else

void board_rgb_write(uint8_t const rgb[]) {
  (void) rgb;
}

#endif

//--------------------------------------------------------------------+
// Timer
//--------------------------------------------------------------------+
void board_timer_start(uint32_t ms) {
  SysTick_Config((SystemCoreClock / 1000) * ms);
}

void board_timer_stop(void) {
  SysTick->CTRL &= ~SysTick_CTRL_ENABLE_Msk;
}

void SysTick_Handler(void) {
  board_timer_handler();
}

int board_uart_write(void const * buf, int len)
{
#if USE_UART
  HAL_UART_Transmit(&UartHandle, (uint8_t*) buf, len, 0xffff);
  return len;
#else
  (void) buf; (void) len;
  return 0;
#endif
}

#ifndef BUILD_NO_TINYUSB
// Forward USB interrupt events to TinyUSB IRQ Handler
void USB_DRD_FS_IRQHandler(void) {
  tud_int_handler(0);
}
#endif

// Required by __libc_init_array in startup code if we are compiling using
// -nostdlib/-nostartfiles.
void _init(void)
{

}
