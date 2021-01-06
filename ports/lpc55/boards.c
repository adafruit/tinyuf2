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
#include "tusb.h"

#include "fsl_device_registers.h"
#include "fsl_rtc.h"
#include "fsl_iap.h"
#include "fsl_iap_ffr.h"
#include "fsl_gpio.h"
#include "fsl_usart.h"
#include "fsl_power.h"
#include "fsl_iocon.h"
#include "clock_config.h"

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM DECLARATION
//--------------------------------------------------------------------+

#define IOCON_VBUS_CONFIG        IOCON_PIO_DIG_FUNC7_EN /*!<@brief Digital pin function 7 enabled */

// FLASH
#define NO_CACHE        0xffffffff

#define FLASH_PAGE_SIZE 512
#define FILESYSTEM_BLOCK_SIZE 256

static flash_config_t _flash_config;
static uint32_t _flash_page_addr = NO_CACHE;
static uint8_t  _flash_cache[FLASH_PAGE_SIZE] __attribute__((aligned(4)));

//--------------------------------------------------------------------+
//
//--------------------------------------------------------------------+
void board_flash_init(void)
{
}

uint32_t board_flash_size(void)
{
  return BOARD_FLASH_SIZE;
}

void board_flash_read(uint32_t addr, void* buffer, uint32_t len)
{
  FLASH_Read(&_flash_config, addr, buffer, len);
}

void board_flash_flush(void)
{
  status_t status;
  uint32_t failedAddress, failedData;

  if ( _flash_page_addr == NO_CACHE ) return;

  status = FLASH_VerifyProgram(&_flash_config, _flash_page_addr, FLASH_PAGE_SIZE, (const uint8_t *)_flash_cache, &failedAddress, &failedData);

  if (status != kStatus_Success) {
    TU_LOG1("Erase and Write at address = 0x%08lX\r\n",_flash_page_addr);
    status = FLASH_Erase(&_flash_config, _flash_page_addr, FLASH_PAGE_SIZE, kFLASH_ApiEraseKey);
    status = FLASH_Program(&_flash_config, _flash_page_addr, _flash_cache, FLASH_PAGE_SIZE);
  }

  _flash_page_addr = NO_CACHE;
}

void board_flash_write (uint32_t addr, void const *data, uint32_t len)
{
  uint32_t newAddr = addr & ~(FLASH_PAGE_SIZE - 1);
  int32_t status;
    
  if (newAddr != _flash_page_addr) {
    board_flash_flush();
    _flash_page_addr = newAddr;
    status = FLASH_Read(&_flash_config, newAddr, _flash_cache, FLASH_PAGE_SIZE);
    if (status != kStatus_Success) {
      TU_LOG1("Flash read error at address = 0x%08lX\r\n", _flash_page_addr);
    }
  }
  memcpy(_flash_cache + (addr & (FLASH_PAGE_SIZE - 1)), data, len);
}

uint8_t board_usb_get_serial(uint8_t serial_id[16])
{
  FFR_GetUUID(&_flash_config, serial_id);
  return 16;
}

// Check if application is valid
bool board_app_valid(void)
{
  uint32_t readData[2];
  status_t readStatus;
  // 2nd word is App entry point (reset)
  readStatus = FLASH_Read(&_flash_config, BOARD_FLASH_APP_START, (uint8_t *)readData, 8);
  if (readStatus) {
    if (readStatus == kStatus_FLASH_EccError){
      TU_LOG1("No app present (erased)\r\n");  // Erased flash causes ECC errors
    } else {
      TU_LOG1("Flash read failed status: %ld, \r\n", readStatus);
    }
    return false;
  } else {
    if ((readData[1] >= BOARD_FLASH_APP_START) && (readData[1] < BOARD_FLASH_SIZE)) {
      TU_LOG2("Valid reset vector:  0x%08lX\r\n", readData[1]);
      return true;
    } else {
      TU_LOG1("No app present (invalid vector)\r\n");
      return false;
    }
  }
}

void board_init(void)
{
  // Enable IOCON clock
  CLOCK_EnableClock(kCLOCK_Iocon);

  // Init 96 MHz clock
  BOARD_BootClockFROHF96M();

  // Init RTC for access to DBL_TAP_REG
  RTC_Init(RTC);

  // disable systick
  board_timer_stop();

  // Initialize Pins
  board_pin_init();

#if defined(UART_DEV) && CFG_TUSB_DEBUG
  // Enable UART when debug log is on
  CLOCK_AttachClk(kFRO12M_to_FLEXCOMM0);
  usart_config_t uart_config;
  USART_GetDefaultConfig(&uart_config);
  uart_config.baudRate_Bps = BOARD_UART_BAUDRATE;
  uart_config.enableTx     = true;
  uart_config.enableRx     = true;
  USART_Init(UART_DEV, &uart_config, 12000000);
#endif

  // Flash needs to be initialized to check for a valid image
  if (FLASH_Init(&_flash_config) == kStatus_Success) {
    TU_LOG2("Flash init successfull!!\r\n");
  } else {
    TU_LOG1("\r\n\r\n\t---- FLASH ERROR! ----\r\n");
  }
}

void board_dfu_init(void)
{
  // USB VBUS
  /* PORT0 PIN22 (coords: 78) is configured as USB0_VBUS */
  IOCON_PinMuxSet(IOCON, 0U, 22U, IOCON_VBUS_CONFIG);

  // USB Controller
  POWER_DisablePD(kPDRUNCFG_PD_USB0_PHY); /*Turn on USB0 Phy */
  POWER_DisablePD(kPDRUNCFG_PD_USB1_PHY); /*< Turn on USB1 Phy */

  /* reset the IP to make sure it's in reset state. */
  RESET_PeripheralReset(kUSB0D_RST_SHIFT_RSTn);
  RESET_PeripheralReset(kUSB0HSL_RST_SHIFT_RSTn);
  RESET_PeripheralReset(kUSB0HMR_RST_SHIFT_RSTn);
  RESET_PeripheralReset(kUSB1H_RST_SHIFT_RSTn);
  RESET_PeripheralReset(kUSB1D_RST_SHIFT_RSTn);
  RESET_PeripheralReset(kUSB1_RST_SHIFT_RSTn);
  RESET_PeripheralReset(kUSB1RAM_RST_SHIFT_RSTn);

#if (defined CFG_TUSB_RHPORT1_MODE) && (CFG_TUSB_RHPORT1_MODE & OPT_MODE_DEVICE)
  CLOCK_EnableClock(kCLOCK_Usbh1);
  /* Put PHY powerdown under software control */
  USBHSH->PORTMODE = USBHSH_PORTMODE_SW_PDCOM_MASK;
  /* According to reference mannual, device mode setting has to be set by access usb host register */
  USBHSH->PORTMODE |= USBHSH_PORTMODE_DEV_ENABLE_MASK;
  /* enable usb1 host clock */
  CLOCK_DisableClock(kCLOCK_Usbh1);
#endif

#if (defined CFG_TUSB_RHPORT0_MODE) && (CFG_TUSB_RHPORT0_MODE & OPT_MODE_DEVICE)
  // Enable USB Clock Adjustments to trim the FRO for the full speed controller
  ANACTRL->FRO192M_CTRL |= ANACTRL_FRO192M_CTRL_USBCLKADJ_MASK;
  CLOCK_SetClkDiv(kCLOCK_DivUsb0Clk, 1, false);
  CLOCK_AttachClk(kFRO_HF_to_USB0_CLK);
  /* enable usb0 host clock */
  CLOCK_EnableClock(kCLOCK_Usbhsl0);
  /*According to reference mannual, device mode setting has to be set by access usb host register */
  USBFSH->PORTMODE |= USBFSH_PORTMODE_DEV_ENABLE_MASK;
  /* disable usb0 host clock */
  CLOCK_DisableClock(kCLOCK_Usbhsl0);
  CLOCK_EnableUsbfs0DeviceClock(kCLOCK_UsbfsSrcFro, CLOCK_GetFreq(kCLOCK_FroHf)); /* enable USB Device clock */
#endif

  TU_LOG2("FRO192M_CTRL:  0x%08lX\r\n", ANACTRL->FRO192M_CTRL);
}

void board_dfu_complete(void)
{
  NVIC_SystemReset();
}

void board_app_jump(void)
{
  uint32_t *vectorTable = (uint32_t*)BOARD_FLASH_APP_START;
  uint32_t sp = vectorTable[0];
  uint32_t pc = vectorTable[1];

  typedef void (*app_entry_t)(void);

  uint32_t s_stackPointer = 0;
  uint32_t s_applicationEntry = 0;
  app_entry_t s_application = 0;

  s_stackPointer = sp;
  s_applicationEntry = pc;
  s_application = (app_entry_t)s_applicationEntry;

  // Disable UART interrupt
  //    USART_DisableInterrupts(USART0, kUSART_RxLevelInterruptEnable | kUSART_RxErrorInterruptEnable);
  // Disable Interrupts
  NVIC->ICER[0] = 0xFFFFFFFF;
  NVIC->ICER[1] = 0xFFFFFFFF;
  // Change MSP and PSP
  __set_MSP(s_stackPointer);
  __set_PSP(s_stackPointer);

  SCB->VTOR = BOARD_FLASH_APP_START;

  // Jump to application
  s_application();

  // Should never reach here.
  __NOP();
}

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
  USART_WriteBlocking(UART_DEV, (uint8_t *)buf, len);
  return len;
}

// Forward USB interrupt events to TinyUSB IRQ Handler
#ifndef TINYUF2_SELF_UPDATE
void USB0_IRQHandler(void)
{
  tud_int_handler(0);
}

void USB1_IRQHandler(void)
{
  tud_int_handler(1);
}
#endif

#ifdef TINYUF2_SELF_UPDATE
void board_self_update(const uint8_t * bootloader_bin, uint32_t bootloader_len)
{
  (void) bootloader_bin;
  (void) bootloader_len;
}
#endif
