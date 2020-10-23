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
#include "stm32f4xx.h"
#include "stm32f4xx_hal_conf.h"

#include "tusb.h"

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM DECLARATION
//--------------------------------------------------------------------+

#define STM32_UUID ((uint32_t *)0x1FFF7A10)

#define UARTx                 USART3
#define UART_GPIO_PORT        GPIOB
#define UART_GPIO_AF          GPIO_AF7_USART3
#define UART_TX_PIN           GPIO_PIN_10
#define UART_RX_PIN           GPIO_PIN_11

UART_HandleTypeDef UartHandle;

void board_led_write(uint32_t state);

//--------------------------------------------------------------------+
// Forward USB interrupt events to TinyUSB IRQ Handler
//--------------------------------------------------------------------+
void OTG_FS_IRQHandler(void)
{
  tud_int_handler(0);
}

// enable all LED, Button, Uart, USB clock
static void all_rcc_clk_enable(void)
{
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();

  __HAL_RCC_USART3_CLK_ENABLE(); // Uart module
}

/**
  * @brief  System Clock Configuration
  *         The system Clock is configured as follow :
  *            System Clock source            = PLL (HSE)
  *            SYSCLK(Hz)                     = 168000000
  *            HCLK(Hz)                       = 168000000
  *            AHB Prescaler                  = 1
  *            APB1 Prescaler                 = 4
  *            APB2 Prescaler                 = 2
  *            HSE Frequency(Hz)              = 12000000
  *            PLL_M                          = HSE_VALUE/1000000
  *            PLL_N                          = 336
  *            PLL_P                          = 2
  *            PLL_Q                          = 7
  *            VDD(V)                         = 3.3
  *            Main regulator output voltage  = Scale1 mode
  *            Flash Latency(WS)              = 5
  * @param  None
  * @retval None
  */
static void SystemClock_Config(void)
{
  RCC_ClkInitTypeDef RCC_ClkInitStruct;
  RCC_OscInitTypeDef RCC_OscInitStruct;

  /* Enable Power Control clock */
  __HAL_RCC_PWR_CLK_ENABLE();

  /* The voltage scaling allows optimizing the power consumption when the device is
     clocked below the maximum system frequency, to update the voltage scaling value
     regarding system frequency refer to product datasheet.  */
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

  /* Enable HSE Oscillator and activate PLL with HSE as source */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLM = HSE_VALUE/1000000;
  RCC_OscInitStruct.PLL.PLLN = 336;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = 7;
  HAL_RCC_OscConfig(&RCC_OscInitStruct);

  /* Select PLL as system clock source and configure the HCLK, PCLK1 and PCLK2
     clocks dividers */
  RCC_ClkInitStruct.ClockType = (RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2);
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV4;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV2;
  HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_5);
}

void board_init(void)
{
  // 1ms tick timer
  SysTick_Config(SystemCoreClock / 1000);
  SystemClock_Config();
  SystemCoreClockUpdate();

  all_rcc_clk_enable();

  GPIO_InitTypeDef  GPIO_InitStruct;

#ifdef BUTTON_PIN
  GPIO_InitStruct.Pin = BUTTON_PIN;
  GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  GPIO_InitStruct.Speed = GPIO_SPEED_FAST;
  HAL_GPIO_Init(BUTTON_PORT, &GPIO_InitStruct);
#endif

#ifdef LED_PIN
  GPIO_InitStruct.Pin = LED_PIN;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  GPIO_InitStruct.Speed = GPIO_SPEED_FAST;
  HAL_GPIO_Init(LED_PORT, &GPIO_InitStruct);

  board_led_write(0);
#endif

#ifdef NEOPIXEL_PIN
  GPIO_InitStruct.Pin = NEOPIXEL_PIN;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  GPIO_InitStruct.Speed = GPIO_SPEED_FAST;
  HAL_GPIO_Init(NEOPIXEL_PORT, &GPIO_InitStruct);
#endif

  // Uart
  GPIO_InitStruct.Pin       = UART_TX_PIN | UART_RX_PIN;
  GPIO_InitStruct.Mode      = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull      = GPIO_PULLUP;
  GPIO_InitStruct.Speed     = GPIO_SPEED_FREQ_HIGH;
  GPIO_InitStruct.Alternate = UART_GPIO_AF;
  HAL_GPIO_Init(UART_GPIO_PORT, &GPIO_InitStruct);

  // USB Pin Init
  // PA9- VUSB, PA10- ID, PA11- DM, PA12- DP

  /* Configure DM DP Pins */
  GPIO_InitStruct.Pin = GPIO_PIN_11 | GPIO_PIN_12;
  GPIO_InitStruct.Speed = GPIO_SPEED_HIGH;
  GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Alternate = GPIO_AF10_OTG_FS;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /* Configure VBUS Pin */
  GPIO_InitStruct.Pin = GPIO_PIN_9;
  GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /* This for ID line debug */
  GPIO_InitStruct.Pin = GPIO_PIN_10;
  GPIO_InitStruct.Mode = GPIO_MODE_AF_OD;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  GPIO_InitStruct.Speed = GPIO_SPEED_HIGH;
  GPIO_InitStruct.Alternate = GPIO_AF10_OTG_FS;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  // Enable USB OTG clock
  __HAL_RCC_USB_OTG_FS_CLK_ENABLE();

  // Enable VBUS sense (B device) via pin PA9
  USB_OTG_FS->GCCFG &= ~USB_OTG_GCCFG_NOVBUSSENS;
  USB_OTG_FS->GCCFG |= USB_OTG_GCCFG_VBUSBSEN;
}

void board_dfu_complete(void)
{
  NVIC_SystemReset();
}

uint8_t board_usb_get_serial(uint8_t serial_id[16])
{
  uint8_t const len = 12;
  memcpy(serial_id, STM32_UUID, len);
  return len;
}

//--------------------------------------------------------------------+
// LED pattern
//--------------------------------------------------------------------+

void board_led_write(uint32_t state)
{
  HAL_GPIO_WritePin(LED_PORT, LED_PIN, state ? LED_STATE_ON : (1-LED_STATE_ON));
}

#if USE_RGB

#define MAGIC_800_INT   900000  // ~1.11 us  -> 1.2  field
#define MAGIC_800_T0H  2800000  // ~0.36 us -> 0.44 field
#define MAGIC_800_T1H  1350000  // ~0.74 us -> 0.84 field

void board_rgb_write(uint8_t const rgb[])
{
  // neopixel color order is GRB
  uint8_t const pixels[3] = { rgb[1] & NEOPIXEL_BRIGHTNESS, rgb[0] & NEOPIXEL_BRIGHTNESS, rgb[2] & NEOPIXEL_BRIGHTNESS };
  uint32_t numBytes = 3;

  uint8_t const *p = pixels, *end = p + numBytes;
  uint8_t pix = *p++, mask = 0x80;
  uint32_t start = 0;
  uint32_t cyc = 0;

  //assumes 800_000Hz frequency
  //Theoretical values here are 800_000 -> 1.25us, 2500000->0.4us, 1250000->0.8us
  //TODO: try to get dynamic weighting working again
  uint32_t sys_freq = HAL_RCC_GetSysClockFreq();
  uint32_t interval = sys_freq/MAGIC_800_INT;
  uint32_t t0 = (sys_freq/MAGIC_800_T0H);
  uint32_t t1 = (sys_freq/MAGIC_800_T1H);

  __disable_irq();

  // Enable DWT in debug core. Useable when interrupts disabled, as opposed to Systick->VAL
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
      pix       = *p++;
      mask = 0x80;
    }
  }

  // Enable interrupts again
  __enable_irq();
}

#endif

void SysTick_Handler (void)
{

}

// Required by __libc_init_array in startup code if we are compiling using
// -nostdlib/-nostartfiles.
void _init(void)
{

}
