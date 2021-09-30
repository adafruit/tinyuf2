#include "board_api.h"
#include "stm32l4xx_hal.h"

void Error_Handler(void) {
    for (;;) {

    }
}

#define HAL_CHECK(x) if (x != HAL_OK) Error_Handler()

//--------------------------------------------------------------------+
// RCC Clock
//--------------------------------------------------------------------+
void clock_init(void)
{
    // enable the debugger while sleeping. Todo move somewhere more central (kind of generally useful in a debug build)
  SET_BIT(DBGMCU->CR, DBGMCU_CR_DBG_SLEEP);

  //  Set tick interrupt priority, default HAL value is intentionally invalid
  //  Without this, USB does not function.
  HAL_InitTick((1UL << __NVIC_PRIO_BITS) - 1UL);


  RCC_ClkInitTypeDef RCC_ClkInitStruct = {};
  RCC_OscInitTypeDef RCC_OscInitStruct = {};
  RCC_PeriphCLKInitTypeDef PeriphClkInitStruct = {};


  /* Enable Power Control clock */
   __HAL_RCC_LSEDRIVE_CONFIG(RCC_LSEDRIVE_LOW);
  __HAL_RCC_PWR_CLK_ENABLE();

   if (HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1_BOOST) != HAL_OK) {
      Error_Handler();
   }

   /* Activate PLL with MSI , stabilizied via PLL by LSE */
   RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_LSE | RCC_OSCILLATORTYPE_MSI;
   RCC_OscInitStruct.MSIState = RCC_MSI_ON;
   RCC_OscInitStruct.LSEState = RCC_LSE_ON;
   RCC_OscInitStruct.MSIClockRange = RCC_MSIRANGE_11;
   RCC_OscInitStruct.MSICalibrationValue = RCC_MSICALIBRATION_DEFAULT;
   RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
   RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_MSI;
   RCC_OscInitStruct.PLL.PLLM = 6;
   RCC_OscInitStruct.PLL.PLLN = 30;
   RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV5;
   RCC_OscInitStruct.PLL.PLLQ = RCC_PLLQ_DIV2;
   RCC_OscInitStruct.PLL.PLLR = RCC_PLLR_DIV2;
   HAL_CHECK(HAL_RCC_OscConfig(&RCC_OscInitStruct));

   /* Enable MSI Auto-calibration through LSE */
   HAL_RCCEx_EnableMSIPLLMode();

   /* Select PLL as system clock source and configure the HCLK, PCLK1 and PCLK2
      clocks dividers */
   RCC_ClkInitStruct.ClockType = (RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2);
   RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
   RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
   RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV4;
   RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV2;
   HAL_CHECK(HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_5));

    PeriphClkInitStruct.PeriphClockSelection = RCC_PERIPHCLK_USB | RCC_PERIPHCLK_RTC;
    PeriphClkInitStruct.UsbClockSelection = RCC_USBCLKSOURCE_MSI;
    PeriphClkInitStruct.RTCClockSelection = RCC_RTCCLKSOURCE_LSE;
    HAL_CHECK(HAL_RCCEx_PeriphCLKConfig(&PeriphClkInitStruct));

}
