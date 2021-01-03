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
#include "fsl_sctimer.h"

#include "clock_config.h"

//--------------------------------------------------------------------+
// Neopixel Driver
//--------------------------------------------------------------------+
#define NEO_SCT           SCT0
#define NEO_MATCH_PERIOD  0
#define NEO_MATCH_0       1
#define NEO_MATCH_1       2
#define NEO_EVENT_RISE    2
#define NEO_EVENT_FALL_0  0
#define NEO_EVENT_FALL_1  1
#define NEO_EVENT_NEXT    3
#define NEO_EVENT_START   4
#define NEO_SCT_OUTPUT    6
#define NEO_STATE_IDLE    24

volatile uint32_t _neopixel_array[NEOPIXEL_NUMBER] = {0};
volatile uint32_t _neopixel_count = NEOPIXEL_NUMBER;

void neopixel_int_handler(void){
  uint32_t eventFlag = NEO_SCT->EVFLAG;
  if (eventFlag & (1 << NEO_EVENT_NEXT)) {
    _neopixel_count += 1;
    if (_neopixel_count < (NEOPIXEL_NUMBER)) {
      NEO_SCT->EV[NEO_EVENT_FALL_0].STATE = 0xFFFFFF & (~_neopixel_array[_neopixel_count]);
      NEO_SCT->CTRL &= ~(SCT_CTRL_HALT_L_MASK);
    }
  }
  NEO_SCT->EVFLAG = eventFlag;
}

void SCT0_DriverIRQHandler(void){
  neopixel_int_handler();
  SDK_ISR_EXIT_BARRIER;
}

void neopixel_set(uint32_t pixel, uint32_t color){
  if (pixel < NEOPIXEL_NUMBER) { 
    _neopixel_array[pixel] = color;
  }
}

void neopixel_update(void){
  while (_neopixel_count < NEOPIXEL_NUMBER) { 
    _neopixel_count = 0;
    NEO_SCT->EV[NEO_EVENT_FALL_0].STATE = 0xFFFFFF & (~_neopixel_array[0]);
    NEO_SCT->CTRL &= ~(SCT_CTRL_HALT_L_MASK);
  }
}

void neopixel_init(void) {
  CLOCK_EnableClock(kCLOCK_Sct0);
  RESET_PeripheralReset(kSCT0_RST_SHIFT_RSTn);

  NEO_SCT->CONFIG = (
    SCT_CONFIG_UNIFY(1) | 
    SCT_CONFIG_CLKMODE(kSCTIMER_System_ClockMode) | 
    SCT_CONFIG_NORELOAD_L(1) );
  NEO_SCT->CTRL = ( 
    SCT_CTRL_HALT_L(1) |
    SCT_CTRL_CLRCTR_L(1) );

  NEO_SCT->MATCH[NEO_MATCH_PERIOD] = 120;
  NEO_SCT->MATCH[NEO_MATCH_0] = 30;
  NEO_SCT->MATCH[NEO_MATCH_1] = 60;
  NEO_SCT->EV[NEO_EVENT_START].STATE = (1 << NEO_STATE_IDLE);
  NEO_SCT->EV[NEO_EVENT_START].CTRL = (
    kSCTIMER_OutputLowEvent | SCT_EV_CTRL_IOSEL(NEO_SCT_OUTPUT) | 
    SCT_EV_CTRL_STATELD(1) | SCT_EV_CTRL_STATEV(23));
  NEO_SCT->EV[NEO_EVENT_RISE].STATE = 0xFFFFFE;
  NEO_SCT->EV[NEO_EVENT_RISE].CTRL = (
    kSCTIMER_MatchEventOnly | SCT_EV_CTRL_MATCHSEL(NEO_MATCH_PERIOD) | 
    SCT_EV_CTRL_STATELD(0) | SCT_EV_CTRL_STATEV(31));
  NEO_SCT->EV[NEO_EVENT_FALL_0].STATE = 0x0;
  NEO_SCT->EV[NEO_EVENT_FALL_0].CTRL = (
    kSCTIMER_MatchEventOnly | SCT_EV_CTRL_MATCHSEL(NEO_MATCH_0) | 
    SCT_EV_CTRL_STATELD(0) );
  NEO_SCT->EV[NEO_EVENT_FALL_1].STATE = 0xFFFFFF;
  NEO_SCT->EV[NEO_EVENT_FALL_1].CTRL = (
    kSCTIMER_MatchEventOnly | SCT_EV_CTRL_MATCHSEL(NEO_MATCH_1) | 
    SCT_EV_CTRL_STATELD(0) );
  NEO_SCT->EV[NEO_EVENT_NEXT].STATE = 0x1;
  NEO_SCT->EV[NEO_EVENT_NEXT].CTRL = (
    kSCTIMER_MatchEventOnly | SCT_EV_CTRL_MATCHSEL(NEO_MATCH_PERIOD) | 
    SCT_EV_CTRL_STATELD(1) | SCT_EV_CTRL_STATEV(NEO_STATE_IDLE));

  NEO_SCT->LIMIT = (1 << NEO_EVENT_START) | (1 << NEO_EVENT_RISE) | (1 << NEO_EVENT_NEXT);
  NEO_SCT->HALT = (1 << NEO_EVENT_NEXT);
  NEO_SCT->START = (1 << NEO_EVENT_START);

  NEO_SCT->OUT[NEO_SCT_OUTPUT].SET = (1 << NEO_EVENT_START) | (1 << NEO_EVENT_RISE);
  NEO_SCT->OUT[NEO_SCT_OUTPUT].CLR = (1 << NEO_EVENT_FALL_0) | (1 << NEO_EVENT_FALL_1) | (1 << NEO_EVENT_NEXT);
  
  NEO_SCT->STATE = NEO_STATE_IDLE; 
  NEO_SCT->OUTPUT = 0x0;
  NEO_SCT->RES = SCT_RES_O6RES(0x2);
  NEO_SCT->EVEN = (1 << NEO_EVENT_NEXT);
  EnableIRQ(SCT0_IRQn);

  neopixel_set(0, 0x101000);
  neopixel_set(1, 0x101000);
  neopixel_update();
}

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

  GPIO_PinInit(GPIO, BUTTON_PORT, BUTTON_PIN, &(gpio_pin_config_t){kGPIO_DigitalInput, 0});

  GPIO_PinInit(GPIO, LED_PORT, LED_PIN, &(gpio_pin_config_t){kGPIO_DigitalOutput, 1});

  neopixel_init();
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
  uint32_t color = (rgb[1]<<16) | (rgb[0]<<8) | (rgb[2]);  // Neopixel is GRB
  neopixel_set(0, color);
  neopixel_set(1, color);
  neopixel_update();
}

//--------------------------------------------------------------------+
// Button API
//--------------------------------------------------------------------+

uint32_t board_button_read(void)
{
  // active low
  return (BUTTON_STATE_ACTIVE == GPIO_PinRead(GPIO, BUTTON_PORT, BUTTON_PIN));
}

