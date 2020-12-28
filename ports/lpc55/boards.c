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
#include "fsl_gpio.h"
#include "fsl_usart.h"
#include "fsl_power.h"
#include "fsl_iocon.h"

#include "clock_config.h"

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM DECLARATION
//--------------------------------------------------------------------+

#define IOCON_VBUS_CONFIG        0x0107u /*!<@brief Digital pin function 7 enabled */

void board_init(void)
{
  // Enable IOCON clock
  CLOCK_EnableClock(kCLOCK_Iocon);

  // Init 96 MHz clock
  BOARD_BootClockFROHF96M();

  // disable systick
  board_timer_stop();

  // Initialize Pins
  board_pin_init();
 
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

#if (defined USB_DEVICE_CONFIG_LPCIP3511HS) && (USB_DEVICE_CONFIG_LPCIP3511HS)
  CLOCK_EnableClock(kCLOCK_Usbh1);
  /* Put PHY powerdown under software control */
  *((uint32_t *)(USBHSH_BASE + 0x50)) = USBHSH_PORTMODE_SW_PDCOM_MASK;
  /* According to reference mannual, device mode setting has to be set by access usb host register */
  *((uint32_t *)(USBHSH_BASE + 0x50)) |= USBHSH_PORTMODE_DEV_ENABLE_MASK;
  /* enable usb1 host clock */
  CLOCK_DisableClock(kCLOCK_Usbh1);
#endif

#if 1 || (defined USB_DEVICE_CONFIG_LPCIP3511FS) && (USB_DEVICE_CONFIG_LPCIP3511FS)
  CLOCK_SetClkDiv(kCLOCK_DivUsb0Clk, 1, false);
  CLOCK_AttachClk(kFRO_HF_to_USB0_CLK);
  /* enable usb0 host clock */
  CLOCK_EnableClock(kCLOCK_Usbhsl0);
  /*According to reference mannual, device mode setting has to be set by access usb host register */
  *((uint32_t *)(USBFSH_BASE + 0x5C)) |= USBFSH_PORTMODE_DEV_ENABLE_MASK;
  /* disable usb0 host clock */
  CLOCK_DisableClock(kCLOCK_Usbhsl0);
  CLOCK_EnableUsbfs0DeviceClock(kCLOCK_UsbfsSrcFro, CLOCK_GetFreq(kCLOCK_FroHf)); /* enable USB Device clock */
#endif
}

void board_dfu_complete(void)
{
  NVIC_SystemReset();
}

/* Defined in board_flash.c 
bool board_app_valid(void)
{
  return false;
} */

void board_app_jump(void)
{
    uint32_t *vectorTable = (uint32_t*)BOARD_FLASH_APP_START;
    uint32_t sp = vectorTable[0];
    uint32_t pc = vectorTable[1];

    typedef void(*app_entry_t)(void);

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
    USART_WriteBlocking(UART_DEV, (uint8_t*)buf, len);
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
