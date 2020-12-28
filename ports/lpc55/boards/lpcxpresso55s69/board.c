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

#define IOCON_PIO_DIG_FUNC0_EN   0x0100u /*!<@brief Digital pin function 0 enabled */
#define IOCON_PIO_DIG_FUNC1_EN   0x0101u /*!<@brief Digital pin function 1 enabled */
#define IOCON_PIO_DIG_FUNC2_EN   0x0102u /*!<@brief Digital pin function 2 enabled */



void board_pin_init(void)
{
  GPIO_PortInit(GPIO, 0);
  GPIO_PortInit(GPIO, 1);

  /* PORT0 PIN29 (coords: 92) is configured as FC0_RXD_SDA_MOSI_DATA */
  IOCON_PinMuxSet(IOCON, 0U, 29U, IOCON_PIO_DIG_FUNC1_EN);
  /* PORT0 PIN30 (coords: 94) is configured as FC0_TXD_SCL_MISO_WS */
  IOCON_PinMuxSet(IOCON, 0U, 30U, IOCON_PIO_DIG_FUNC1_EN);
  /* PORT0 PIN5 (coords: 88) is configured as PIO0_5 (button) */
  IOCON_PinMuxSet(IOCON, 0U, 5U, IOCON_PIO_DIG_FUNC0_EN);
  /* PORT1 PINS 4,6,7 is configured as GPIO (RGB LED) */
  IOCON_PinMuxSet(IOCON, 1U, 4U, IOCON_PIO_DIG_FUNC0_EN);
  IOCON_PinMuxSet(IOCON, 1U, 6U, IOCON_PIO_DIG_FUNC0_EN);
  IOCON_PinMuxSet(IOCON, 1U, 7U, IOCON_PIO_DIG_FUNC0_EN);

  GPIO_PinInit(GPIO, BUTTON_PORT, BUTTON_PIN, &(gpio_pin_config_t){kGPIO_DigitalInput, 0});

  GPIO_PinInit(GPIO, BOARD_LED_RED_GPIO_PORT, BOARD_LED_RED_GPIO_PIN, &(gpio_pin_config_t){kGPIO_DigitalOutput, 0});
  GPIO_PinInit(GPIO, BOARD_LED_GREEN_GPIO_PORT, BOARD_LED_GREEN_GPIO_PIN, &(gpio_pin_config_t){kGPIO_DigitalOutput, 0});
  GPIO_PinInit(GPIO, BOARD_LED_BLUE_GPIO_PORT, BOARD_LED_BLUE_GPIO_PIN, &(gpio_pin_config_t){kGPIO_DigitalOutput, 0});

}

//--------------------------------------------------------------------+
// LED pattern
//--------------------------------------------------------------------+

void board_led_write(uint32_t value)
{
  // TODO PWM for fading
  (void) value;
//  GPIO_PinWrite(GPIO, LED_PORT, LED_PIN, state ? LED_STATE_ON : (1-LED_STATE_ON));
}

// Write color to rgb strip
void board_rgb_write(uint8_t const rgb[]) { 
    if (rgb[0]) {
      GPIO_PortClear(GPIO, BOARD_LED_RED_GPIO_PORT, 1U << BOARD_LED_RED_GPIO_PIN);
    } else {
      GPIO_PortSet(GPIO, BOARD_LED_RED_GPIO_PORT, 1U << BOARD_LED_RED_GPIO_PIN);
    }
    if (rgb[1]) {
      GPIO_PortClear(GPIO, BOARD_LED_GREEN_GPIO_PORT, 1U << BOARD_LED_GREEN_GPIO_PIN);
    } else {
      GPIO_PortSet(GPIO, BOARD_LED_GREEN_GPIO_PORT, 1U << BOARD_LED_GREEN_GPIO_PIN);
    }
    if (rgb[2]) {
      GPIO_PortClear(GPIO, BOARD_LED_BLUE_GPIO_PORT, 1U << BOARD_LED_BLUE_GPIO_PIN);
    } else {
      GPIO_PortSet(GPIO, BOARD_LED_BLUE_GPIO_PORT, 1U << BOARD_LED_BLUE_GPIO_PIN);
    }
}

uint32_t board_button_read(void)
{
  // active low
  return (BUTTON_STATE_ACTIVE == GPIO_PinRead(GPIO, BUTTON_PORT, BUTTON_PIN));
}

