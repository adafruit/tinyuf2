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
#include "sct_neopixel.h"

#include "clock_config.h"

uint32_t _pixelData[NEOPIXEL_NUMBER] = {0};

//--------------------------------------------------------------------+
// Board Pin Initialization
//--------------------------------------------------------------------+
void board_pin_init(void)
{
  GPIO_PortInit(GPIO, 0);
  GPIO_PortInit(GPIO, 1);

  /* PORT0 PIN29 (coords: 92) is configured as FC0_RXD_SDA_MOSI_DATA */
  IOCON_PinMuxSet(IOCON, 0U, 29U, IOCON_PIO_DIG_FUNC1_EN);
  /* PORT0 PIN30 (coords: 94) is configured as FC0_TXD_SCL_MISO_WS */
  IOCON_PinMuxSet(IOCON, 0U, 30U, IOCON_PIO_DIG_FUNC1_EN);
  /* PORT0 PIN5 (coords: 88) is configured as PIO0_5 (button) */
  IOCON_PinMuxSet(IOCON, BUTTON_PORT, BUTTON_PIN, IOCON_PIO_DIG_FUNC0_EN);
  /* PORT0 PIN1 is configured as GPIO (LED) */
  IOCON_PinMuxSet(IOCON, LED_PORT, LED_PIN, IOCON_PIO_DIG_FUNC0_EN);
  /* PORT0 PIN27 is configured as SCT0 OUT6 (NEOPIXEL) */
  IOCON_PinMuxSet(IOCON, NEOPIXEL_PORT, NEOPIXEL_PIN, IOCON_PIO_DIG_FUNC4_EN);

  // GPIO_PinInit(GPIO, BUTTON_PORT, BUTTON_PIN, &(gpio_pin_config_t){kGPIO_DigitalInput, 0});

  GPIO_PinInit(GPIO, LED_PORT, LED_PIN, &(gpio_pin_config_t){kGPIO_DigitalOutput, 1});

  sctpix_init(NEOPIXEL_TYPE);
  sctpix_addCh(NEOPIXEL_CH, _pixelData, NEOPIXEL_NUMBER);
  sctpix_setPixel(NEOPIXEL_CH, 0, 0x101000);
  sctpix_setPixel(NEOPIXEL_CH, 1, 0x101000);
  sctpix_show();
}

//--------------------------------------------------------------------+
// LED APIs
//--------------------------------------------------------------------+

void board_led_write(uint32_t value)
{
  // TODO PWM for fading
  GPIO_PinWrite(GPIO, LED_PORT, LED_PIN, (uint8_t)value);
}

// Write color to rgb strip
void board_rgb_write(uint8_t const rgb[]) { 
  uint32_t color = 0;    // Neopixel is GRB
  if (rgb[0]) { color += (NEOPIXEL_BRIGHTNESS <<16); }
  if (rgb[1]) { color += (NEOPIXEL_BRIGHTNESS <<8); }
  if (rgb[2]) { color += (NEOPIXEL_BRIGHTNESS); }
  sctpix_setPixel(NEOPIXEL_CH, 0, color);
  sctpix_setPixel(NEOPIXEL_CH, 1, color);
  sctpix_show();
}

