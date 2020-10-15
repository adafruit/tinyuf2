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

#include "boards.h"

#include "esp_rom_gpio.h"
#include "hal/gpio_ll.h"
#include "hal/usb_hal.h"
#include "soc/usb_periph.h"

#include "driver/periph_ctrl.h"
#include "driver/rmt.h"
#include "led_strip.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/timers.h"

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM DECLARATION
//--------------------------------------------------------------------+

#ifdef PIN_NEOPIXEL
static led_strip_t *strip;
#endif

#define RGB_USB_UNMOUNTED   0xff, 0x00, 0x00 // Red
#define RGB_USB_MOUNTED     0x00, 0xff, 0x00 // Green
#define RGB_WRITING         0xcc, 0x66, 0x00
#define RGB_UNKNOWN         0x00, 0x00, 0x88 // for debug

extern int main(void);
static void configure_pins(usb_hal_context_t *usb);

//--------------------------------------------------------------------+
// TinyUSB thread
//--------------------------------------------------------------------+

// static task for usbd
// Increase stack size when debug log is enabled
#define USBD_STACK_SIZE     (4*1024)

static StackType_t  usb_device_stack[USBD_STACK_SIZE];
static StaticTask_t usb_device_taskdef;

// USB Device Driver task
// This top level thread process all usb events and invoke callbacks
void usb_device_task(void* param)
{
  (void) param;

  // RTOS forever loop
  while (1)
  {
    tud_task();
  }
}

void app_main(void)
{
  main();

  // Create a task for tinyusb device stack
  (void) xTaskCreateStatic( usb_device_task, "usbd", USBD_STACK_SIZE, NULL, configMAX_PRIORITIES-2, usb_device_stack, &usb_device_taskdef);
}

//--------------------------------------------------------------------+
// Board API
//--------------------------------------------------------------------+

void board_init(void)
{

#ifdef PIN_LED
//#define BLINK_GPIO 26
//  gpio_pad_select_gpio(BLINK_GPIO);
//  gpio_set_direction(BLINK_GPIO, GPIO_MODE_OUTPUT);
//  gpio_set_drive_capability(BLINK_GPIO, GPIO_DRIVE_CAP_3);
//  gpio_set_level(BLINK_GPIO, 1);
#endif

#ifdef PIN_NEOPIXEL
  // WS2812 Neopixel driver with RMT peripheral
  rmt_config_t config = RMT_DEFAULT_CONFIG_TX(PIN_NEOPIXEL, RMT_CHANNEL_0);
  config.clk_div = 2; // set counter clock to 40MHz

  rmt_config(&config);
  rmt_driver_install(config.channel, 0, 0);

  led_strip_config_t strip_config = LED_STRIP_DEFAULT_CONFIG(NEOPIXEL_NUMBER, (led_strip_dev_t) config.channel);
  strip = led_strip_new_rmt_ws2812(&strip_config);
  strip->clear(strip, 100); // off led
  strip->set_brightness(strip, NEOPIXEL_BRIGHTNESS);
#endif

  // USB Controller Hal init
  periph_module_reset(PERIPH_USB_MODULE);
  periph_module_enable(PERIPH_USB_MODULE);

  usb_hal_context_t hal = {
    .use_external_phy = false // use built-in PHY
  };
  usb_hal_init(&hal);
  configure_pins(&hal);
}

void board_teardown(void)
{

}

static void configure_pins(usb_hal_context_t *usb)
{
  /* usb_periph_iopins currently configures USB_OTG as USB Device.
   * Introduce additional parameters in usb_hal_context_t when adding support
   * for USB Host.
   */
  for (const usb_iopin_dsc_t *iopin = usb_periph_iopins; iopin->pin != -1; ++iopin) {
    if ((usb->use_external_phy) || (iopin->ext_phy_only == 0)) {
      esp_rom_gpio_pad_select_gpio(iopin->pin);
      if (iopin->is_output) {
        esp_rom_gpio_connect_out_signal(iopin->pin, iopin->func, false, false);
      } else {
        esp_rom_gpio_connect_in_signal(iopin->pin, iopin->func, false);
        if ((iopin->pin != GPIO_FUNC_IN_LOW) && (iopin->pin != GPIO_FUNC_IN_HIGH)) {
          gpio_ll_input_enable(&GPIO, iopin->pin);
        }
      }
      esp_rom_gpio_pad_unhold(iopin->pin);
    }
  }
  if (!usb->use_external_phy) {
    gpio_set_drive_capability(USBPHY_DM_NUM, GPIO_DRIVE_CAP_3);
    gpio_set_drive_capability(USBPHY_DP_NUM, GPIO_DRIVE_CAP_3);
  }
}

//--------------------------------------------------------------------+
// LED pattern
//--------------------------------------------------------------------+

#ifdef PIN_NEOPIXEL
TimerHandle_t blinky_tm = NULL;

static void neopixel_set(uint8_t r, uint8_t g, uint8_t b)
{
  strip->set_pixel(strip, 0, r, g, b);
  strip->refresh(strip, 100);
}

void led_blinky_cb(TimerHandle_t xTimer)
{
  (void) xTimer;
  static bool led_state = false;
  led_state = 1 - led_state; // toggle

  if ( led_state )
  {
    neopixel_set(RGB_WRITING);
  }else
  {
    strip->clear(strip, 100);
  }
}
#endif

void board_led_state(uint32_t state)
{
  #ifdef PIN_NEOPIXEL
  switch(state)
  {
    case STATE_BOOTLOADER_STARTED:
    case STATE_USB_UNMOUNTED:
      neopixel_set(RGB_USB_UNMOUNTED);
    break;

    case STATE_USB_MOUNTED:
      neopixel_set(RGB_USB_MOUNTED);
    break;

    case STATE_WRITING_STARTED:
      // soft timer for blinky
      blinky_tm = xTimerCreate(NULL, pdMS_TO_TICKS(50), true, NULL, led_blinky_cb);
      xTimerStart(blinky_tm, 0);
    break;

    case STATE_WRITING_FINISHED:
      xTimerStop(blinky_tm, 0);
      neopixel_set(RGB_WRITING);
    break;

    default:
      neopixel_set(RGB_UNKNOWN);
    break;
  }
  #endif
}
