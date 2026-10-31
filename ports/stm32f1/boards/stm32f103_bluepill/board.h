/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2026 qzydustin
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

// STM32F103C8T6 "Blue Pill": 8 MHz crystal, LED on PC13 (on when low), D+ pulled up by a resistor (R10), no user
// button. Many carry 128 KB of flash; 64 KB is what the part guarantees.

#ifndef BOARD_H_
#define BOARD_H_

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+

#define LED_PORT              GPIOC
#define LED_PIN               GPIO_PIN_13
#define LED_STATE_ON          0

//--------------------------------------------------------------------+
// Flash
//--------------------------------------------------------------------+

#define BOARD_FLASH_SIZE      (64 * 1024)

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

// TODO VID/PID aren't assigned for this board
#define USB_VID           0xcafe
#define USB_PID           0xffff
#define USB_MANUFACTURER  "STM32"
#define USB_PRODUCT       "Blue Pill"

#define UF2_PRODUCT_NAME  USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID      "STM32F103C8-BluePill-v0"
#define UF2_VOLUME_LABEL  "BLUEPILL"
#define UF2_INDEX_URL     "https://stm32-base.org/boards/STM32F103C8T6-Blue-Pill"

//--------------------------------------------------------------------+
// RCC Clock
//--------------------------------------------------------------------+
static inline void clock_init(void)
{
  RCC_ClkInitTypeDef clkinitstruct = {0};
  RCC_OscInitTypeDef oscinitstruct = {0};
  RCC_PeriphCLKInitTypeDef rccperiphclkinit = {0};

  // HSE 8 MHz x 9 = 72 MHz, USB 72 / 1.5 = 48 MHz
  oscinitstruct.OscillatorType  = RCC_OSCILLATORTYPE_HSE;
  oscinitstruct.HSEState        = RCC_HSE_ON;
  oscinitstruct.HSEPredivValue  = RCC_HSE_PREDIV_DIV1;
  oscinitstruct.PLL.PLLMUL      = RCC_PLL_MUL9;
  oscinitstruct.PLL.PLLState    = RCC_PLL_ON;
  oscinitstruct.PLL.PLLSource   = RCC_PLLSOURCE_HSE;
  HAL_RCC_OscConfig(&oscinitstruct);

  rccperiphclkinit.PeriphClockSelection = RCC_PERIPHCLK_USB;
  rccperiphclkinit.UsbClockSelection = RCC_USBCLKSOURCE_PLL_DIV1_5;
  HAL_RCCEx_PeriphCLKConfig(&rccperiphclkinit);

  clkinitstruct.ClockType = (RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2);
  clkinitstruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  clkinitstruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  clkinitstruct.APB1CLKDivider = RCC_HCLK_DIV2;
  clkinitstruct.APB2CLKDivider = RCC_HCLK_DIV1;
  HAL_RCC_ClockConfig(&clkinitstruct, FLASH_LATENCY_2);
}

#endif
