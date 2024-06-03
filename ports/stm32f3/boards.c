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
#include "stm32f3xx_hal.h"

#ifndef BUILD_NO_TINYUSB
#include "tusb.h"
#endif

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM DECLARATION
//--------------------------------------------------------------------+

#define STM32_UUID    ((volatile uint32_t *) UID_BASE)

static UART_HandleTypeDef UartHandle;

static bool reset_by_option_bytes = false;

bool board_reset_by_option_bytes(void)
{
  return reset_by_option_bytes;
}

void board_init(void)
{
  // Check asap to ensure correct reason
  reset_by_option_bytes = !!(__HAL_RCC_GET_FLAG(RCC_FLAG_OBLRST));

  clock_init();
  SystemCoreClockUpdate();

  // disable systick
  board_timer_stop();

  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOE_CLK_ENABLE();

  GPIO_InitTypeDef  GPIO_InitStruct;

  #ifdef BUTTON_PIN
  GPIO_InitStruct.Pin = BUTTON_PIN;
  GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = GPIO_PULLDOWN;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(BUTTON_PORT, &GPIO_InitStruct);
  #endif

  #ifdef LED_PIN
  GPIO_InitStruct.Pin = LED_PIN;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(LED_PORT, &GPIO_InitStruct);

  board_led_write(0);
  #endif

  #if NEOPIXEL_NUMBER
  GPIO_InitStruct.Pin = NEOPIXEL_PIN;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(NEOPIXEL_PORT, &GPIO_InitStruct);
  #endif

  #if defined(UART_DEV) && CFG_TUSB_DEBUG
  UART_CLOCK_ENABLE();

  GPIO_InitStruct.Pin       = UART_TX_PIN | UART_RX_PIN;
  GPIO_InitStruct.Mode      = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull      = GPIO_PULLUP;
  GPIO_InitStruct.Speed     = GPIO_SPEED_FREQ_HIGH;
  GPIO_InitStruct.Alternate = GPIO_AF7_USART2;
  HAL_GPIO_Init(UART_GPIO_PORT, &GPIO_InitStruct);

  UartHandle.Instance        = UART_DEV;
  UartHandle.Init.BaudRate   = 115200;
  UartHandle.Init.WordLength = UART_WORDLENGTH_8B;
  UartHandle.Init.StopBits   = UART_STOPBITS_1;
  UartHandle.Init.Parity     = UART_PARITY_NONE;
  UartHandle.Init.HwFlowCtl  = UART_HWCONTROL_NONE;
  UartHandle.Init.Mode       = UART_MODE_TX_RX;
  HAL_UART_Init(&UartHandle);
  #endif
}

void board_dfu_init(void)
{
  __HAL_RCC_SYSCFG_CLK_ENABLE();
  __HAL_REMAPINTERRUPT_USB_ENABLE();

  GPIO_InitTypeDef  GPIO_InitStruct;
  GPIO_InitStruct.Pin = (GPIO_PIN_11 | GPIO_PIN_12);
  GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  GPIO_InitStruct.Alternate = GPIO_AF14_USB;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  // Enable USB clock
  __HAL_RCC_USB_CLK_ENABLE();
}

void board_reset(void)
{
  NVIC_SystemReset();
}

void board_dfu_complete(void)
{
  NVIC_SystemReset();
}

bool board_app_valid(void)
{
  if((((*(uint32_t*)BOARD_FLASH_APP_START) - BOARD_RAM_START) <= BOARD_RAM_SIZE)) // && ((*(uint32_t*)BOARD_FLASH_APP_START + 4) > BOARD_FLASH_APP_START) && ((*(uint32_t*)BOARD_FLASH_APP_START + 4) < BOARD_FLASH_APP_START + BOARD_FLASH_SIZE)
  {
    return true;
  }
  return false;
}

void board_app_jump(void)
{
  volatile uint32_t const * app_vector = (volatile uint32_t const*) BOARD_FLASH_APP_START;
  uint32_t sp = app_vector[0];
  uint32_t app_entry = app_vector[1];

  GPIO_InitTypeDef  GPIO_InitStruct;
  GPIO_InitStruct.Pin = GPIO_PIN_12;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_12, GPIO_PIN_RESET);

  #ifdef BUTTON_PIN
  HAL_GPIO_DeInit(BUTTON_PORT, BUTTON_PIN);
  #endif

  #ifdef LED_PIN
  HAL_GPIO_DeInit(LED_PORT, LED_PIN);
  #endif

  #if NEOPIXEL_NUMBER
  HAL_GPIO_DeInit(NEOPIXEL_PORT, NEOPIXEL_PIN);
  #endif

  #if defined(UART_DEV) && CFG_TUSB_DEBUG
  HAL_UART_DeInit(&UartHandle);
  HAL_GPIO_DeInit(UART_GPIO_PORT, UART_TX_PIN | UART_RX_PIN);
  UART_CLOCK_DISABLE();
  #endif

  HAL_GPIO_DeInit(GPIOA, GPIO_PIN_12 | GPIO_PIN_11);

  __HAL_RCC_GPIOA_CLK_DISABLE();
  __HAL_RCC_GPIOB_CLK_DISABLE();
  __HAL_RCC_GPIOC_CLK_DISABLE();
  __HAL_RCC_GPIOD_CLK_DISABLE();
  __HAL_RCC_GPIOE_CLK_DISABLE();

  HAL_RCC_DeInit();
  HAL_DeInit();

  SysTick->CTRL = 0;
  SysTick->LOAD = 0;
  SysTick->VAL = 0;

  // Disable all Interrupts
  NVIC->ICER[0] = 0xFFFFFFFF;
  NVIC->ICER[1] = 0xFFFFFFFF;
  NVIC->ICER[2] = 0xFFFFFFFF;
  NVIC->ICER[3] = 0xFFFFFFFF;

  /* switch exception handlers to the application */
  SCB->VTOR = (uint32_t) BOARD_FLASH_APP_START;

  // Set stack pointer
  __set_MSP(sp);

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

void board_rgb_write(uint8_t const rgb[])
{
  // neopixel color order is GRB
  uint8_t const pixels[3] = { apply_percentage(rgb[1]), apply_percentage(rgb[0]), apply_percentage(rgb[2]) };
  uint32_t const numBytes = 3;

  uint8_t const *p = pixels, *end = p + numBytes;
  uint8_t pix = *p++, mask = 0x80;
  uint32_t start = 0;
  uint32_t cyc = 0;

  //assumes 800_000Hz frequency
  //Theoretical values here are 800_000 -> 1.25us, 2500000->0.4us, 1250000->0.8us
  //TODO: try to get dynamic weighting working again
  uint32_t const sys_freq = HAL_RCC_GetSysClockFreq();
  uint32_t const interval = sys_freq/MAGIC_800_INT;
  uint32_t const t0       = sys_freq/MAGIC_800_T0H;
  uint32_t const t1       = sys_freq/MAGIC_800_T1H;

  __disable_irq();

  // Enable DWT in debug core. Usable when interrupts disabled, as opposed to Systick->VAL
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
  DWT->CYCCNT = 0;

  for(;;) {
    cyc = (pix & mask) ? t1 : t0;
    start = DWT->CYCCNT;

    HAL_GPIO_WritePin(NEOPIXEL_PORT, NEOPIXEL_PIN, 1);
    while((DWT->CYCCNT - start) < cyc);

    HAL_GPIO_WritePin(NEOPIXEL_PORT, NEOPIXEL_PIN, 0);
    while((DWT->CYCCNT - start) < interval);

    if(!(mask >>= 1)) {
      if(p >= end) break;
      pix  = *p++;
      mask = 0x80;
    }
  }

  __enable_irq();
}

#else

void board_rgb_write(uint8_t const rgb[])
{
  (void) rgb;
}

#endif

//--------------------------------------------------------------------+
// Timer
//--------------------------------------------------------------------+

void board_timer_start(uint32_t ms)
{
  SysTick_Config( (SystemCoreClock/1000) * ms );
}

void board_timer_stop(void)
{
  SysTick->CTRL &= ~SysTick_CTRL_ENABLE_Msk;
}

void SysTick_Handler (void)
{
  board_timer_handler();
}

int board_uart_write(void const * buf, int len)
{
#if defined(UART_DEV) && CFG_TUSB_DEBUG
  HAL_UART_Transmit(&UartHandle, (uint8_t*) buf, len, 0xffff);
  return len;
#else
  (void) buf; (void) len;
  (void) UartHandle;
  return 0;
#endif
}

#ifndef BUILD_NO_TINYUSB
// Forward USB interrupt events to TinyUSB IRQ Handler
void USB_HP_IRQHandler(void) {
  tud_int_handler(0);
}

// USB low-priority interrupt (Channel 75): Triggered by all USB events
// (Correct transfer, USB reset, etc.). The firmware has to check the
// interrupt source before serving the interrupt.
void USB_LP_IRQHandler(void) {
  tud_int_handler(0);
}

// USB wakeup interrupt (Channel 76): Triggered by the wakeup event from the USB
// Suspend mode.
void USBWakeUp_RMP_IRQHandler(void) {
  tud_int_handler(0);
}

#endif

// Required by __libc_init_array in startup code if we are compiling using
// -nostdlib/-nostartfiles.
__attribute__((used)) void _init(void) {
}
