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
  /* PORT0 PIN1 is configured as GPIO (LED) */
  IOCON_PinMuxSet(IOCON, 0U, 1U, IOCON_PIO_DIG_FUNC0_EN);
  /* PORT1 PINS 4,6,7 is configured as GPIO (RGB LED) */
  IOCON_PinMuxSet(IOCON, 1U, 4U, IOCON_PIO_DIG_FUNC0_EN);
  IOCON_PinMuxSet(IOCON, 1U, 6U, IOCON_PIO_DIG_FUNC0_EN);
  IOCON_PinMuxSet(IOCON, 1U, 7U, IOCON_PIO_DIG_FUNC0_EN);

  // GPIO_PinInit(GPIO, BUTTON_PORT, BUTTON_PIN, &(gpio_pin_config_t){kGPIO_DigitalInput, 0});

  GPIO_PinInit(GPIO, LED_PORT, LED_PIN, &(gpio_pin_config_t){kGPIO_DigitalOutput, 1});

  GPIO_PinInit(GPIO, BOARD_LED_RED_GPIO_PORT, BOARD_LED_RED_GPIO_PIN, &(gpio_pin_config_t){kGPIO_DigitalOutput, 0});
  GPIO_PinInit(GPIO, BOARD_LED_GREEN_GPIO_PORT, BOARD_LED_GREEN_GPIO_PIN, &(gpio_pin_config_t){kGPIO_DigitalOutput, 0});
  GPIO_PinInit(GPIO, BOARD_LED_BLUE_GPIO_PORT, BOARD_LED_BLUE_GPIO_PIN, &(gpio_pin_config_t){kGPIO_DigitalOutput, 0});

}

//--------------------------------------------------------------------+
// LED pattern
//--------------------------------------------------------------------+

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

