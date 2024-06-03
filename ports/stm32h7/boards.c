#include "stm32h7xx_hal.h"
#include "board_api.h"

#define STM32_UUID ((uint32_t *)0x1FF1E800)

void board_init(void)
{
  SCB_EnableICache();
#ifndef RAMCODE
  SCB_EnableDCache();
#endif
  __HAL_RCC_SYSCFG_CLK_ENABLE();
  clock_init();
  SystemCoreClockUpdate();
  SysTick_Config( (SystemCoreClock/1000) );

  // But some boards might end up using them
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOE_CLK_ENABLE();
  __HAL_RCC_GPIOF_CLK_ENABLE();
  __HAL_RCC_GPIOG_CLK_ENABLE();
  __HAL_RCC_GPIOH_CLK_ENABLE();
  __HAL_RCC_GPIOI_CLK_ENABLE();
  __HAL_RCC_GPIOJ_CLK_ENABLE();
  __HAL_RCC_GPIOK_CLK_ENABLE();

  GPIO_InitTypeDef GPIO_InitStruct;

#ifdef BUTTON_PIN
  GPIO_InitStruct.Pin = BUTTON_PIN;
  GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = GPIO_PULLDOWN;
  HAL_GPIO_Init(BUTTON_PORT, &GPIO_InitStruct);
#endif

#ifdef LED_PIN
  GPIO_InitStruct.Pin = LED_PIN;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(LED_PORT, &GPIO_InitStruct);
#endif

#ifndef TINYUF2_SELF_UPDATE
  board_flash_early_init();
#endif // TINYUF2_SELF_UPDATE
}

// Configure USB for DFU
void board_dfu_init(void)
{
  // Not quite sure what an RHPORT is :/
#if BOARD_TUD_RHPORT == 0
  GPIO_InitTypeDef GPIO_InitStruct;

  // Init USB Pins
  // Configure DM DP pins
  // ID line detection pin has to be initialized, or nothing works
  // mini-stm32h7 does not have this pin connected to anything
  GPIO_InitStruct.Pin = GPIO_PIN_10 | GPIO_PIN_11 | GPIO_PIN_12;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Alternate = GPIO_AF10_OTG2_HS;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  // https://community.st.com/s/question/0D50X00009XkYZLSA3/stm32h7-nucleo-usb-fs-cdc
  // TODO: Board init actually works fine without this line.
  HAL_PWREx_EnableUSBVoltageDetector();
  __HAL_RCC_USB2_OTG_FS_CLK_ENABLE();

  // No VBUS Sensing capabilities on the board
  // TODO: add a compile switch and Vbus sensing capability
  // Disable Vbus sense (B device) via pin PA9
  USB_OTG_FS->GCCFG &= ~USB_OTG_GCCFG_VBDEN;

  // B-peripheral session valid override enable
  USB_OTG_FS->GOTGCTL |= USB_OTG_GOTGCTL_BVALOEN;
  USB_OTG_FS->GOTGCTL |= USB_OTG_GOTGCTL_BVALOVAL;

#elif BOARD_TUD_RHPORT == 1
  // TODO: implement whatever this is
  #error "Sorry, not implemented yet"
#endif

}

void board_reset(void)
{
  // Clean Cache
  SCB_CleanDCache();
  NVIC_SystemReset();
}

void board_dfu_complete(void)
{
  // Clean Cache
  SCB_CleanDCache();
  NVIC_SystemReset();
}

bool board_app_valid(void)
{
  uint32_t app_addr = board_get_app_start_address();
  uint32_t app_vector[2u] = { 0u, 0u };
  board_flash_read(app_addr, app_vector, 8u);

  // 1st word should be in SRAM region and aligned
  switch ((app_vector[0] & 0xFFFF0003u))
  {
    case 0x00000000u: // ITCM 64K       [0x0000_0000u--0x0000_FFFFu]
    case 0x20000000u: // DTCM 64K       [0x2000_0000u--0x2000_FFFFu]
    case 0x20010000u: // DTCM 64K       [0x2001_0000u--0x2001_FFFFu]
    case 0x24000000u: // AXI SRAM 512K  [0x2400_0000u--0x2407_FFFFu]
    case 0x30010000u: // SRAM1 64K      [0x3001_0000u--0x3001_FFFFu]
    case 0x30020000u: // SRAM2 64K      [0x3002_0000u--0x3002_FFFFu]
    case 0x30030000u: // SRAM2 64K      [0x3003_0000u--0x3003_FFFFu]
    case 0x30040000u: // SRAM3 32K      [0x3004_0000u--0x3004_7FFFu]
    case 0x38000000u: // SRAM4 64K      [0x3800_0000u--0x3800_FFFFu]
    case 0x38800000u: // Backup SRAM 4K [0x3880_0000u--0x3880_0FFFu]
      break;
    default:
      return false;
  }

  // 2nd word should be application reset

  // If the Reset_Handler is in the later 64KB of PFLASH then it's valid
  if (IS_PFLASH_ADDR(app_addr) && (IS_PFLASH_ADDR(app_vector[1]))) return true;

  // If the Reset_Handler in QSPI in points to QSPI flash then it's valid
  if (IS_QSPI_ADDR(app_addr) && IS_QSPI_ADDR(app_vector[1])) return true;

  // If Reset_Handler in RAM points to RAM
  if (IS_AXISRAM_ADDR(app_addr) && IS_AXISRAM_ADDR(app_vector[1])) return true;
  // TODO: support downloads validation in other RAM regions as well

  return false;
}

void board_app_jump(void)
{
  // wrap up flash - qspi can go into mmap mode
  board_flash_deinit();

  // Get saved boot address
  uint32_t app_addr = board_get_app_start_address();
  volatile uint32_t const * app_vector = (volatile uint32_t const *) app_addr;

#ifdef BUTTON_PIN
  HAL_GPIO_DeInit(BUTTON_PORT, BUTTON_PIN);
#endif

#ifdef LED_PIN
  HAL_GPIO_DeInit(LED_PORT, LED_PIN);
#endif

  __HAL_RCC_GPIOA_CLK_DISABLE();
  __HAL_RCC_GPIOB_CLK_DISABLE();
  __HAL_RCC_GPIOC_CLK_DISABLE();
  __HAL_RCC_GPIOD_CLK_DISABLE();
  __HAL_RCC_GPIOE_CLK_DISABLE();
  __HAL_RCC_GPIOF_CLK_DISABLE();
  __HAL_RCC_GPIOG_CLK_DISABLE();
  __HAL_RCC_GPIOH_CLK_DISABLE();
  __HAL_RCC_GPIOI_CLK_DISABLE();
  __HAL_RCC_GPIOJ_CLK_DISABLE();
  __HAL_RCC_GPIOK_CLK_DISABLE();
  // Lotsa GPIOs

  HAL_RCC_DeInit();
  SCB_DisableICache();
  SCB_DisableDCache();

  // Clear temporary boot address
  board_clear_temp_boot_addr();

  // Setup VTOR to point to application vectors
  SCB->VTOR = (uint32_t) app_addr;

  // Set stack pointer
  __set_MSP(app_vector[0]);
  __set_PSP(app_vector[0]);

  TUF2_LOG1("App address: %08lx\r\n", app_vector[1]);

  // Jump to application reset vector
  asm("bx %0" :: "r"(app_vector[1]));

}

// USB Get_Serial response
uint8_t board_usb_get_serial(uint8_t serial_id[16])
{
  uint8_t const len = 12;
  memcpy(serial_id, STM32_UUID, len);
  return len;
}

//--------------------------------------------------------------------+
// Timer
//--------------------------------------------------------------------+

void board_timer_start(uint32_t ms)
{
  // TODO: check if ST HAL requires Systick timing to always be 1ms
  SysTick_Config((SystemCoreClock/1000) * ms);
}

void board_timer_stop(void)
{
  SysTick->CTRL &= ~SysTick_CTRL_ENABLE_Msk;
}

int board_uart_write(void const * buf, int len)
{
  (void) buf;
  (void) len;
  return 0;
}

#ifdef TINYUF2_SELF_UPDATE
void board_self_update(const uint8_t * bootloader_bin, uint32_t bootloader_len)
{
  HAL_FLASH_Unlock();
  FLASH_EraseInitTypeDef flashErase = {0};
  flashErase.TypeErase = FLASH_TYPEERASE_MASSERASE;
  flashErase.Banks = FLASH_BANK_1;
  flashErase.Sector = FLASH_SECTOR_0;
  flashErase.NbSectors = 1;
  flashErase.VoltageRange = FLASH_VOLTAGE_RANGE_1;
  HAL_FLASHEx_Erase(&flashErase, NULL);
  for ( uint32_t i = 0; i < bootloader_len; i+= 4*FLASH_NB_32BITWORD_IN_FLASHWORD ) {
    if (HAL_OK != HAL_FLASH_Program(FLASH_TYPEPROGRAM_FLASHWORD, 0x08000000U + i, (uint32_t) &bootloader_bin[i]))
    {
      TUF2_LOG1("Bootloader update failure\r\n");
      return;
    }
  }
  HAL_FLASH_Lock();
  board_reset();
}
#endif
