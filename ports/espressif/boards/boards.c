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

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/timers.h"

#include "esp_rom_gpio.h"
#include "hal/gpio_ll.h"
#include "hal/usb_hal.h"
#include "soc/usb_periph.h"

#include "driver/periph_ctrl.h"
#include "driver/rmt.h"

#include "esp_partition.h"
#include "esp_ota_ops.h"
#include "board_api.h"

#ifndef TINYUF2_SELF_UPDATE
#include "tusb.h"
#endif

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM DECLARATION
//--------------------------------------------------------------------+

static esp_timer_handle_t timer_hdl;

#ifdef NEOPIXEL_PIN
#include "led_strip.h"
static led_strip_t *strip;
#endif

#ifdef DOTSTAR_PIN_DATA
#include "driver/spi_master.h"

void dotstar_init(void);
void dotstar_write(uint8_t const rgb[]);
#endif

#ifdef TCA9554_ADDR
#include "esp_err.h"
#include "driver/i2c.h"
#endif

#ifdef LED_PIN
#include "driver/ledc.h"
ledc_channel_config_t ledc_channel =
{
  .channel    = LEDC_CHANNEL_0,
  .duty       = 0,
  .gpio_num   = LED_PIN,
  .speed_mode = LEDC_LOW_SPEED_MODE,
  .hpoint     = 0,
  .timer_sel  = LEDC_TIMER_0
};
#endif

#ifdef DISPLAY_PIN_SCK
#include "lcd.h"
#endif

#if BOARD_INIT_CUSTOM
extern bool board_init_extension();
#endif

extern int main(void);
static void configure_pins(usb_hal_context_t *usb);
static void internal_timer_cb(void* arg);

//--------------------------------------------------------------------+
// TinyUSB thread
//--------------------------------------------------------------------+

#ifdef TINYUF2_SELF_UPDATE

void app_main(void)
{
  main();
}

#else

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

#endif

//--------------------------------------------------------------------+
// Board API
//--------------------------------------------------------------------+

void board_init(void)
{
// Peripheral control through I2C Expander
#ifdef TCA9554_ADDR
  int i2c_num = I2C_MASTER_NUM;
  i2c_config_t conf = {
      .mode = I2C_MODE_MASTER,
      .sda_io_num = I2C_MASTER_SDA_IO,
      .scl_io_num = I2C_MASTER_SCL_IO,
      .sda_pullup_en = GPIO_PULLUP_ENABLE,
      .scl_pullup_en = GPIO_PULLUP_ENABLE,
      .master.clk_speed = I2C_MASTER_FREQ_HZ,
  };
  i2c_param_config(i2c_num, &conf);
  i2c_driver_install(i2c_num, conf.mode, I2C_MASTER_RX_BUF_DISABLE, I2C_MASTER_TX_BUF_DISABLE, 0);

  // Turn on PERI_POWER that is controlled by TC9554 I2C Expander
  i2c_cmd_handle_t cmd = i2c_cmd_link_create();
  i2c_master_start(cmd);
  i2c_master_write_byte(cmd, TCA9554_ADDR << 1 | I2C_MASTER_WRITE, true);
  i2c_master_write_byte(cmd, TCA9554_CONFIGURATION_REG, true);
  i2c_master_write_byte(cmd, TCA9554_DEFAULT_CONFIG, true);
  i2c_master_stop(cmd);
  i2c_master_cmd_begin(i2c_num, cmd, 1000 / portTICK_RATE_MS);
  i2c_cmd_link_delete(cmd);
  vTaskDelay(30 / portTICK_RATE_MS);
  cmd = i2c_cmd_link_create();
  i2c_master_start(cmd);
  i2c_master_write_byte(cmd, TCA9554_ADDR << 1 | I2C_MASTER_WRITE, true);
  i2c_master_write_byte(cmd, TCA9554_OUTPUT_PORT_REG, true);
  i2c_master_write_byte(cmd, TCA9554_DEFAULT_VALUE, true);
  i2c_master_stop(cmd);
  i2c_master_cmd_begin(i2c_num, cmd, 1000 / portTICK_RATE_MS);
  i2c_cmd_link_delete(cmd);
  i2c_driver_delete(i2c_num);

#endif

#ifdef LED_PIN
  ledc_timer_config_t ledc_timer =
  {
    .duty_resolution = LEDC_TIMER_8_BIT      , // resolution of PWM duty
    .freq_hz         = 5000                  , // frequency of PWM signal
    .speed_mode      = LEDC_LOW_SPEED_MODE   , // timer mode
    .timer_num       = ledc_channel.timer_sel, // timer index
    .clk_cfg         = LEDC_AUTO_CLK         , // Auto select the source clock
  };
  ledc_timer_config(&ledc_timer);
  ledc_channel_config(&ledc_channel);
#endif

#ifdef NEOPIXEL_PIN
  #ifdef NEOPIXEL_POWER_PIN
  gpio_reset_pin(NEOPIXEL_POWER_PIN);
  gpio_set_direction(NEOPIXEL_POWER_PIN, GPIO_MODE_OUTPUT);
  gpio_set_level(NEOPIXEL_POWER_PIN, NEOPIXEL_POWER_STATE);
  #endif

  // WS2812 Neopixel driver with RMT peripheral
  rmt_config_t config = RMT_DEFAULT_CONFIG_TX(NEOPIXEL_PIN, RMT_CHANNEL_0);
  config.clk_div = 2; // set counter clock to 40MHz

  rmt_config(&config);
  rmt_driver_install(config.channel, 0, 0);

  led_strip_config_t strip_config = LED_STRIP_DEFAULT_CONFIG(NEOPIXEL_NUMBER, (led_strip_dev_t) config.channel);
  strip = led_strip_new_rmt_ws2812(&strip_config);
  strip->clear(strip, 100); // off led
  strip->set_brightness(strip, NEOPIXEL_BRIGHTNESS);
#endif

#ifdef DOTSTAR_PIN_DATA
  dotstar_init();
#endif

#if BOARD_INIT_CUSTOM
  board_init_extension();
#endif

  // Set up timer
  const esp_timer_create_args_t periodic_timer_args = { .callback = internal_timer_cb };
  esp_timer_create(&periodic_timer_args, &timer_hdl);
}

void board_dfu_init(void)
{
  // USB Controller Hal init
  periph_module_reset(PERIPH_USB_MODULE);
  periph_module_enable(PERIPH_USB_MODULE);

  usb_hal_context_t hal = {
    .use_external_phy = false // use built-in PHY
  };
  usb_hal_init(&hal);
  configure_pins(&hal);
}

void board_reset(void)
{
  esp_restart();
}

void board_dfu_complete(void)
{
  // Set partition OTA0 as bootable and reset
  esp_ota_set_boot_partition(esp_partition_find_first(ESP_PARTITION_TYPE_APP, ESP_PARTITION_SUBTYPE_APP_OTA_0, NULL));
  esp_restart();
}

bool board_app_valid(void)
{
  // esp32s2 is always enter DFU mode
  return false;
}

void board_app_jump(void)
{
  // nothing to do
}

uint8_t board_usb_get_serial(uint8_t serial_id[16])
{
  // use factory default MAC as serial ID
  esp_efuse_mac_get_default(serial_id);
  return 6;
}

void board_led_write(uint32_t value)
{
  (void) value;

#ifdef LED_PIN
  ledc_set_duty(ledc_channel.speed_mode, ledc_channel.channel, value);
  ledc_update_duty(ledc_channel.speed_mode, ledc_channel.channel);
#endif
}

void board_rgb_write(uint8_t const rgb[])
{
#ifdef NEOPIXEL_PIN
  for(uint32_t i=0; i<NEOPIXEL_NUMBER; i++)
  {
    strip->set_pixel(strip, i, rgb[0], rgb[1], rgb[2]);
  }
  strip->refresh(strip, 100);
#endif

#ifdef DOTSTAR_PIN_DATA
  dotstar_write(rgb);
#endif
}

//--------------------------------------------------------------------+
// Timer
//--------------------------------------------------------------------+

static void internal_timer_cb(void*  arg)
{
  (void) arg;
  board_timer_handler();
}

void board_timer_start(uint32_t ms)
{
  esp_timer_stop(timer_hdl);
  esp_timer_start_periodic(timer_hdl, ms*1000);
}

void board_timer_stop(void)
{
  esp_timer_stop(timer_hdl);
}

//--------------------------------------------------------------------+
// Display
//--------------------------------------------------------------------+

#ifdef DISPLAY_PIN_SCK

#define LCD_SPI   SPI2_HOST

spi_device_handle_t _display_spi;

void board_display_init(void)
{
  spi_bus_config_t bus_cfg = {
    .miso_io_num     = DISPLAY_PIN_MISO,
    .mosi_io_num     = DISPLAY_PIN_MOSI,
    .sclk_io_num     = DISPLAY_PIN_SCK,
    .quadwp_io_num   = -1,
    .quadhd_io_num   = -1,
    .max_transfer_sz = PARALLEL_LINES * 320 * 2 + 8
  };

  spi_device_interface_config_t devcfg = {
    .clock_speed_hz = 10 * 1000 * 1000,              /*!< Clock out at 10 MHz */
    .mode           = 0,                             /*!< SPI mode 0 */
    .spics_io_num   = DISPLAY_PIN_CS,                /*!< CS pin */
    .queue_size     = 7,                             /*!< We want to be able to queue 7 transactions at a time */
    .pre_cb         = lcd_spi_pre_transfer_callback, /*!< Specify pre-transfer callback to handle D/C line */
  };

  /*!< Initialize the SPI bus */
  ESP_ERROR_CHECK(spi_bus_initialize(LCD_SPI, &bus_cfg, SPI_DMA_CH_AUTO));

  /*!< Attach the LCD to the SPI bus */
  ESP_ERROR_CHECK(spi_bus_add_device(LCD_SPI, &devcfg, &_display_spi));

  /**< Initialize the LCD */
  ESP_ERROR_CHECK(lcd_init(_display_spi));
}

void board_display_draw_line(int y, uint16_t* pixel_color, uint32_t pixel_num)
{
  (void) pixel_num; // same as DISPLAY_HEIGHT
  lcd_draw_lines(_display_spi, y, (uint16_t*) pixel_color);
}

#endif

//--------------------------------------------------------------------+
// DotStar
//--------------------------------------------------------------------+
#ifdef DOTSTAR_PIN_DATA

#define DOTSTAR_SPI   SPI3_HOST

spi_device_handle_t _dotstar_spi;
uint8_t _dotstar_data[ (1+DOTSTAR_NUMBER+1) * 4];

void dotstar_init(void)
{
  #ifdef DOTSTAR_PIN_PWR
  gpio_reset_pin(DOTSTAR_PIN_PWR);
  gpio_set_direction(DOTSTAR_PIN_PWR, GPIO_MODE_OUTPUT);
  gpio_set_level(DOTSTAR_PIN_PWR, DOTSTAR_POWER_STATE);
  #endif

  spi_bus_config_t bus_cfg =
  {
    .miso_io_num     = -1,
    .mosi_io_num     = DOTSTAR_PIN_DATA,
    .sclk_io_num     = DOTSTAR_PIN_SCK,
    .quadwp_io_num   = -1,
    .quadhd_io_num   = -1,
    .max_transfer_sz = sizeof(_dotstar_data)
  };

  spi_device_interface_config_t devcfg =
  {
    .clock_speed_hz = 10 * 1000000, // 10 Mhz
    .mode           = 0,
    .spics_io_num   = -1,
    .queue_size     = 8,
  };

  /*!< Initialize the SPI bus */
  ESP_ERROR_CHECK(spi_bus_initialize(DOTSTAR_SPI, &bus_cfg, SPI_DMA_CH_AUTO));

  /*!< Attach the LCD to the SPI bus */
  ESP_ERROR_CHECK(spi_bus_add_device(DOTSTAR_SPI, &devcfg, &_dotstar_spi));
}

void dotstar_write(uint8_t const rgb[])
{
  // convert from 0-255 (8 bit) to 0-31 (5 bit)
  uint8_t const ds_brightness = (DOTSTAR_BRIGHTNESS * 32) / 256;

  // start frame
  _dotstar_data[0] = _dotstar_data[1] = _dotstar_data[2] = _dotstar_data[3] = 0;

  uint8_t* color = _dotstar_data+4;

  for(uint8_t i=0; i<DOTSTAR_NUMBER; i++)
  {
    *color++ = 0xE0 | ds_brightness;
    *color++ = rgb[2];
    *color++ = rgb[1];
    *color++ = rgb[0];
  }

  // end frame
  // Four end-frame bytes are seemingly indistinguishable from a white
  // pixel, and empirical testing suggests it can be left out...but it's
  // always a good idea to follow the datasheet, in case future hardware
  // revisions are more strict (e.g. might mandate use of end-frame
  // before start-frame marker). i.e. let's not remove this. But after
  // testing a bit more the suggestion is to use at least (numLeds+1)/2
  // high values (1) or (numLeds+15)/16 full bytes as EndFrame. For details
  *color++ = 0xff;
  *color++ = 0xff;
  *color++ = 0xff;
  *color++ = 0xff;

  static spi_transaction_t xact =
  {
    .length    = (sizeof(_dotstar_data) - 4 + (DOTSTAR_NUMBER+15)/16 )*8, // length in bits, see end frame not above
    .tx_buffer = _dotstar_data
  };

  spi_device_queue_trans(_dotstar_spi, &xact, portMAX_DELAY);
}

#endif

//--------------------------------------------------------------------+
// Helper
//--------------------------------------------------------------------+
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
