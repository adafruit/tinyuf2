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
#include "fsl_power.h"
#include "fsl_iocon.h"

#include "clock_config.h"

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM DECLARATION
//--------------------------------------------------------------------+

#define IOCON_PIO_ASW_DIS_EN     0x00u   /*!<@brief Analog switch is closed (enabled), only for A0 version */
#define IOCON_PIO_ASW_EN         0x0400u /*!<@brief Analog switch is closed (enabled) */
#define IOCON_PIO_DIGITAL_EN     0x0100u /*!<@brief Enables digital function */
#define IOCON_PIO_FUNC0          0x00u   /*!<@brief Selects pin function 0 */
#define IOCON_PIO_FUNC1          0x01u   /*!<@brief Selects pin function 1 */
#define IOCON_PIO_FUNC7          0x07u   /*!<@brief Selects pin function 7 */
#define IOCON_PIO_INV_DI         0x00u   /*!<@brief Input function is not inverted */
#define IOCON_PIO_MODE_INACT     0x00u   /*!<@brief No addition pin function */
#define IOCON_PIO_MODE_PULLUP    0x20u   /*!<@brief Selects pull-up function */
#define IOCON_PIO_OPENDRAIN_DI   0x00u   /*!<@brief Open drain is disabled */
#define IOCON_PIO_SLEW_STANDARD  0x00u   /*!<@brief Standard mode, output slew rate control is enabled */

void board_init(void)
{
  // Enable IOCON clock
  CLOCK_EnableClock(kCLOCK_Iocon);

  // Init 96 MHz clock
  BOARD_BootClockFROHF96M();

  // disable systick
  board_timer_stop();

//  GPIO_PortInit(GPIO, BUTTON_PORT);

  // LED
  GPIO_PortInit(GPIO, LED_PORT);
  gpio_pin_config_t const led_config = { kGPIO_DigitalOutput, 0};
  GPIO_PinInit(GPIO, LED_PORT, LED_PIN, &led_config);
  board_led_write(true);
}

void board_dfu_init(void)
{
  // USB VBUS
  const uint32_t port0_pin22_config = (
      IOCON_PIO_FUNC7         | /* Pin is configured as USB0_VBUS */
      IOCON_PIO_MODE_INACT    | /* No addition pin function */
      IOCON_PIO_SLEW_STANDARD | /* Standard mode, output slew rate control is enabled */
      IOCON_PIO_INV_DI        | /* Input function is not inverted */
      IOCON_PIO_DIGITAL_EN    | /* Enables digital function */
      IOCON_PIO_OPENDRAIN_DI    /* Open drain is disabled */
  );
  /* PORT0 PIN22 (coords: 78) is configured as USB0_VBUS */
  IOCON_PinMuxSet(IOCON, 0U, 22U, port0_pin22_config);

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

bool board_app_valid(void)
{
  return false;
}

void board_app_jump(void)
{
}

uint8_t board_usb_get_serial(uint8_t serial_id[16])
{
  (void) serial_id;
  return 0;
}

//--------------------------------------------------------------------+
// LED pattern
//--------------------------------------------------------------------+

void board_led_write(uint32_t state)
{
  // TODO PWM for fading
  GPIO_PinWrite(GPIO, LED_PORT, LED_PIN, state ? LED_STATE_ON : (1-LED_STATE_ON));
}

void board_rgb_write(uint8_t const rgb[])
{
  (void) rgb;
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
  (void) buf; (void) len;
  return 0;
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
