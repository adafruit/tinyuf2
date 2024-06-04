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

#ifndef BOARD_H_
#define BOARD_H_

#ifdef __cplusplus
extern "C" {
#endif

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+

#define LED_PORT              GPIOE
#define LED_PIN               GPIO_PIN_3
#define LED_STATE_ON          1

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+

#define BUTTON_PORT           GPIOC
#define BUTTON_PIN            GPIO_PIN_13
#define BUTTON_STATE_ACTIVE   1

//--------------------------------------------------------------------+
// Flash
//--------------------------------------------------------------------+

// Flash size of the board
#define BOARD_FLASH_SIZE  (8 * 1024 * 1024)
#define BOARD_FLASH_SECTORS 1

//--------------------------------------------------------------------+
// External QSPI Flash
//--------------------------------------------------------------------+
#define BOARD_QSPI_FLASH_SIZE     (8 * 1024 * 1024) // 8MB

//--------------------------------------------------------------------+
// External SPI Flash
//--------------------------------------------------------------------+
#define BOARD_SPI_FLASH_SIZE      (8 * 1024 * 1024) // 8MB

#define SPI_FLASH_CS_PIN GPIO_PIN_6
#define SPI_FLASH_CS_PORT GPIOD

#define SPI_FLASH_EN()  HAL_GPIO_WritePin(SPI_FLASH_CS_PORT, SPI_FLASH_CS_PIN, GPIO_PIN_RESET)
#define SPI_FLASH_DIS() HAL_GPIO_WritePin(SPI_FLASH_CS_PORT, SPI_FLASH_CS_PIN, GPIO_PIN_SET)

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID           0x239A
#define USB_PID           0x005D
#define USB_MANUFACTURER  "STM32"
#define USB_PRODUCT       "STM32FH750VBT6"

#define UF2_PRODUCT_NAME  USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID      "STM32H750VB-MiniSTM-v1.1"
#define UF2_VOLUME_LABEL  "MiniSTM32H7"
#define UF2_INDEX_URL     "https://github.com/WeActStudio/MiniSTM32H7xx"

#define USB_NO_VBUS_PIN   1
#define BOARD_TUD_RHPORT  0

//--------------------------------------------------------------------+
// UART
//--------------------------------------------------------------------+

// #define UART_DEV              USART2
// #define UART_CLOCK_ENABLE     __HAL_RCC_USART2_CLK_ENABLE
// #define UART_CLOCK_DISABLE    __HAL_RCC_USART2_CLK_DISABLE
// #define UART_GPIO_PORT        GPIOA
// #define UART_GPIO_AF          GPIO_AF7_USART2
// #define UART_TX_PIN           GPIO_PIN_2
// #define UART_RX_PIN           GPIO_PIN_3

//--------------------------------------------------------------------+
// DISPLAY
//--------------------------------------------------------------------+
#define DISPLAY_BL_PIN    GPIO_PIN_10
#define DISPLAY_CS_PIN    GPIO_PIN_11
#define DISPLAY_SCK_PIN   GPIO_PIN_12
#define DISPLAY_CTRL_PIN  GPIO_PIN_13
#define DISPLAY_MOSI_PIN  GPIO_PIN_14
#define DISPLAY_PORT      GPIOE
// The display is 160x80 but the code expects a larger framebuffer
// The display is misconfigured, to make the existing framebuffer look pretty
// on the screen. The complete framebuffer is not displayed
#define DISPLAY_HEIGHT    128
#define DISPLAY_WIDTH     161
// The display title looks horrid
#define DISPLAY_TITLE     ""

//--------------------------------------------------------------------+
// RCC Clock
//--------------------------------------------------------------------+
static inline void clock_init(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};
  RCC_PeriphCLKInitTypeDef PeriphClkInitStruct = {0};

  // Supply configuration update enable
  HAL_PWREx_ConfigSupply(PWR_LDO_SUPPLY);

  // Configure the main internal regulator output voltage
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE2);
  while(!__HAL_PWR_GET_FLAG(PWR_FLAG_VOSRDY)) {}

  // Configure the PLL clock source
  __HAL_RCC_PLL_PLLSOURCE_CONFIG(RCC_PLLSOURCE_HSE);

  // Initializes the CPU, AHB and APB busses clocks
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_LSI|RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.LSIState = RCC_LSI_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLM = 5;
  RCC_OscInitStruct.PLL.PLLN = 96;
  RCC_OscInitStruct.PLL.PLLP = 2;
  RCC_OscInitStruct.PLL.PLLQ = 2;
  RCC_OscInitStruct.PLL.PLLR = 2;
  RCC_OscInitStruct.PLL.PLLRGE = RCC_PLL1VCIRANGE_2;
  RCC_OscInitStruct.PLL.PLLVCOSEL = RCC_PLL1VCOWIDE;
  RCC_OscInitStruct.PLL.PLLFRACN = 0;
  HAL_RCC_OscConfig(&RCC_OscInitStruct);

  // Initializes the CPU, AHB and APB busses clocks
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2
                              |RCC_CLOCKTYPE_D3PCLK1|RCC_CLOCKTYPE_D1PCLK1;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.SYSCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB3CLKDivider = RCC_APB3_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_APB1_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_APB2_DIV1;
  RCC_ClkInitStruct.APB4CLKDivider = RCC_APB4_DIV1;
  HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_1);

  PeriphClkInitStruct.PeriphClockSelection = RCC_PERIPHCLK_RTC|RCC_PERIPHCLK_SPI4
                              |RCC_PERIPHCLK_SPI1|RCC_PERIPHCLK_USB
                              |RCC_PERIPHCLK_QSPI;
  PeriphClkInitStruct.PLL3.PLL3M = 10;
  PeriphClkInitStruct.PLL3.PLL3N = 96;
  PeriphClkInitStruct.PLL3.PLL3P = 5;
  PeriphClkInitStruct.PLL3.PLL3Q = 5;
  PeriphClkInitStruct.PLL3.PLL3R = 2;
  PeriphClkInitStruct.PLL3.PLL3RGE = RCC_PLL3VCIRANGE_1;
  PeriphClkInitStruct.PLL3.PLL3VCOSEL = RCC_PLL3VCOWIDE;
  PeriphClkInitStruct.PLL3.PLL3FRACN = 0;
  PeriphClkInitStruct.QspiClockSelection = RCC_QSPICLKSOURCE_D1HCLK;
  PeriphClkInitStruct.Spi123ClockSelection = RCC_SPI123CLKSOURCE_PLL;
  PeriphClkInitStruct.Spi45ClockSelection = RCC_SPI45CLKSOURCE_D2PCLK1;
  PeriphClkInitStruct.UsbClockSelection = RCC_USBCLKSOURCE_PLL3;
  PeriphClkInitStruct.RTCClockSelection = RCC_RTCCLKSOURCE_LSI;
  HAL_RCCEx_PeriphCLKConfig(&PeriphClkInitStruct);

  // Enable USB Voltage detector
  HAL_PWREx_EnableUSBVoltageDetector();
}

//--------------------------------------------------------------------+
// SPI DISPLAY
//--------------------------------------------------------------------+
#define DISPLAY_CMD_RESET  HAL_GPIO_WritePin(DISPLAY_PORT, DISPLAY_CTRL_PIN, GPIO_PIN_SET)
#define DISPLAY_CMD_SET    HAL_GPIO_WritePin(DISPLAY_PORT, DISPLAY_CTRL_PIN, GPIO_PIN_RESET)

#define DISPLAY_DIS HAL_GPIO_WritePin(DISPLAY_PORT, DISPLAY_CS_PIN, GPIO_PIN_SET)
#define DISPLAY_EN  HAL_GPIO_WritePin(DISPLAY_PORT, DISPLAY_CS_PIN, GPIO_PIN_RESET)

#define DISPLAY_RST

#define DISPLAY_BL_DIS  HAL_GPIO_WritePin(DISPLAY_PORT, DISPLAY_BL_PIN, GPIO_PIN_SET)
#define DISPLAY_BL_EN   HAL_GPIO_WritePin(DISPLAY_PORT, DISPLAY_BL_PIN, GPIO_PIN_RESET)

static inline void display_init(SPI_HandleTypeDef  *pspi)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  GPIO_InitStruct.Pin = DISPLAY_CS_PIN | DISPLAY_CTRL_PIN | DISPLAY_BL_PIN;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(DISPLAY_PORT, &GPIO_InitStruct);


  GPIO_InitStruct.Pin = DISPLAY_SCK_PIN | DISPLAY_MOSI_PIN;
  GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_MEDIUM;
  GPIO_InitStruct.Alternate = GPIO_AF5_SPI4;
  HAL_GPIO_Init(DISPLAY_PORT, &GPIO_InitStruct);

  __HAL_RCC_SPI4_CLK_ENABLE();

  pspi->Instance = SPI4;
  pspi->Init.Mode = SPI_MODE_MASTER;
  pspi->Init.Direction = SPI_DIRECTION_1LINE;
  pspi->Init.DataSize = SPI_DATASIZE_8BIT;
  pspi->Init.CLKPolarity = SPI_POLARITY_LOW;
  pspi->Init.CLKPhase = SPI_PHASE_1EDGE;
  pspi->Init.NSS = SPI_NSS_SOFT;
  pspi->Init.BaudRatePrescaler = SPI_BAUDRATEPRESCALER_8;
  pspi->Init.FirstBit = SPI_FIRSTBIT_MSB;
  pspi->Init.TIMode = SPI_TIMODE_DISABLE;
  pspi->Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;
  pspi->Init.CRCPolynomial = 0x0;
  pspi->Init.NSSPMode = SPI_NSS_PULSE_ENABLE;
  pspi->Init.NSSPolarity = SPI_NSS_POLARITY_LOW;
  pspi->Init.FifoThreshold = SPI_FIFO_THRESHOLD_01DATA;
  pspi->Init.TxCRCInitializationPattern = SPI_CRC_INITIALIZATION_ALL_ZERO_PATTERN;
  pspi->Init.RxCRCInitializationPattern = SPI_CRC_INITIALIZATION_ALL_ZERO_PATTERN;
  pspi->Init.MasterSSIdleness = SPI_MASTER_SS_IDLENESS_00CYCLE;
  pspi->Init.MasterInterDataIdleness = SPI_MASTER_INTERDATA_IDLENESS_00CYCLE;
  pspi->Init.MasterReceiverAutoSusp = SPI_MASTER_RX_AUTOSUSP_DISABLE;
  pspi->Init.MasterKeepIOState = SPI_MASTER_KEEP_IO_STATE_DISABLE;
  pspi->Init.IOSwap = SPI_IO_SWAP_DISABLE;

  HAL_SPI_Init(pspi);
}

//--------------------------------------------------------------------+
// QSPI and SPI FLash
//--------------------------------------------------------------------+
// Check SB3 it should have a 0 ohm

static inline void qspi_flash_init(QSPI_HandleTypeDef * pqspi)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  __HAL_RCC_QSPI_CLK_ENABLE();

  GPIO_InitStruct.Pin = GPIO_PIN_2;
  GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
  GPIO_InitStruct.Alternate = GPIO_AF9_QUADSPI;
  HAL_GPIO_Init(GPIOE, &GPIO_InitStruct);

  GPIO_InitStruct.Pin = GPIO_PIN_2;
  GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
  GPIO_InitStruct.Alternate = GPIO_AF9_QUADSPI;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

  GPIO_InitStruct.Pin = GPIO_PIN_11|GPIO_PIN_12|GPIO_PIN_13;
  GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
  GPIO_InitStruct.Alternate = GPIO_AF9_QUADSPI;
  HAL_GPIO_Init(GPIOD, &GPIO_InitStruct);

  GPIO_InitStruct.Pin = GPIO_PIN_6;
  GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
  GPIO_InitStruct.Alternate = GPIO_AF10_QUADSPI;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

  // HAL_I2CEx_EnableFastModePlus(SYSCFG_PMCR_I2C_PB6_FMP);
  pqspi->Instance = QUADSPI;
  pqspi->Init.ClockPrescaler = 2-1;
  pqspi->Init.FifoThreshold = 1;
  pqspi->Init.SampleShifting = QSPI_SAMPLE_SHIFTING_HALFCYCLE;
  pqspi->Init.FlashSize = 23-1;
  pqspi->Init.ChipSelectHighTime = QSPI_CS_HIGH_TIME_6_CYCLE;
  pqspi->Init.ClockMode = QSPI_CLOCK_MODE_3;
  pqspi->Init.FlashID = QSPI_FLASH_ID_1;
  pqspi->Init.DualFlash = QSPI_DUALFLASH_DISABLE;
  HAL_QSPI_Init(pqspi);
}

static inline void spi_flash_init(SPI_HandleTypeDef * pspi)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  GPIO_InitStruct.Pin = SPI_FLASH_CS_PIN;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(SPI_FLASH_CS_PORT, &GPIO_InitStruct);

  GPIO_InitStruct.Pin = GPIO_PIN_7;
  GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_MEDIUM;
  GPIO_InitStruct.Alternate = GPIO_AF5_SPI1;
  HAL_GPIO_Init(GPIOD, &GPIO_InitStruct);

  GPIO_InitStruct.Pin = GPIO_PIN_3|GPIO_PIN_4;
  GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_MEDIUM;
  GPIO_InitStruct.Alternate = GPIO_AF5_SPI1;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

  __HAL_RCC_SPI1_CLK_ENABLE();
  pspi->Instance = SPI1;
  pspi->Init.Mode = SPI_MODE_MASTER;
  pspi->Init.Direction = SPI_DIRECTION_2LINES;
  pspi->Init.DataSize = SPI_DATASIZE_8BIT;
  pspi->Init.CLKPolarity = SPI_POLARITY_LOW;
  pspi->Init.CLKPhase = SPI_PHASE_1EDGE;
  pspi->Init.NSS = SPI_NSS_SOFT;
  pspi->Init.BaudRatePrescaler = SPI_BAUDRATEPRESCALER_4;
  pspi->Init.FirstBit = SPI_FIRSTBIT_MSB;
  pspi->Init.TIMode = SPI_TIMODE_DISABLE;
  pspi->Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;
  pspi->Init.CRCPolynomial = 0x0;
  pspi->Init.NSSPMode = SPI_NSS_PULSE_ENABLE;
  pspi->Init.NSSPolarity = SPI_NSS_POLARITY_LOW;
  pspi->Init.FifoThreshold = SPI_FIFO_THRESHOLD_01DATA;
  pspi->Init.TxCRCInitializationPattern = SPI_CRC_INITIALIZATION_ALL_ZERO_PATTERN;
  pspi->Init.RxCRCInitializationPattern = SPI_CRC_INITIALIZATION_ALL_ZERO_PATTERN;
  pspi->Init.MasterSSIdleness = SPI_MASTER_SS_IDLENESS_00CYCLE;
  pspi->Init.MasterInterDataIdleness = SPI_MASTER_INTERDATA_IDLENESS_00CYCLE;
  pspi->Init.MasterReceiverAutoSusp = SPI_MASTER_RX_AUTOSUSP_DISABLE;
  pspi->Init.MasterKeepIOState = SPI_MASTER_KEEP_IO_STATE_DISABLE;
  pspi->Init.IOSwap = SPI_IO_SWAP_DISABLE;
  HAL_SPI_Init(pspi);
}

#ifdef __cplusplus
}
#endif

#endif
