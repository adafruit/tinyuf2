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
#include "freertos/semphr.h"

#include "hal/gpio_ll.h"

#include "esp_private/usb_phy.h"
#include "soc/usb_pins.h"

#include "soc/usb_periph.h"
#include "esp_private/periph_ctrl.h"

#include "esp_partition.h"
#include "esp_ota_ops.h"
#include "esp_mac.h"
#include "esp_timer.h"
#include "esp_rom_gpio.h"

#include "driver/gpio.h"

#include "board_api.h"

#ifndef BUILD_NO_TINYUSB
#include "tusb.h"
#endif

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM DECLARATION
//--------------------------------------------------------------------+

static esp_timer_handle_t timer_hdl;

#ifdef NEOPIXEL_PIN
#include "led_strip.h"
static led_strip_handle_t led_strip;
#endif

#ifdef DOTSTAR_PIN_DATA
#include "driver/spi_master.h"

void dotstar_init(void);
void dotstar_write(uint8_t const rgb[]);
#endif

#if defined(TCA9554_ADDR) || defined(AW9523_ADDR)
#include "esp_err.h"
#include "driver/i2c.h"
#endif

#ifdef LED_PIN
#include "driver/ledc.h"
ledc_channel_config_t ledc_channel = {
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
static void internal_timer_cb(void* arg);

//--------------------------------------------------------------------+
// TinyUSB thread
//--------------------------------------------------------------------+

#ifdef BUILD_NO_TINYUSB
void app_main(void) {
  main();
}
#else

// static task for usbd
// Increase stack size when debug log is enabled
#define USBD_STACK_SIZE     (4*1024)

static StackType_t usb_device_stack[USBD_STACK_SIZE];
static StaticTask_t usb_device_taskdef;

// USB Device Driver task
// This top level thread process all usb events and invoke callbacks
void usb_device_task(void* param) {
  (void) param;

  // RTOS forever loop
  while (1) {
    tud_task();
  }
}

void app_main(void) {
  main();

  // Create a task for tinyusb device stack
  (void) xTaskCreateStatic(usb_device_task, "usbd", USBD_STACK_SIZE, NULL, configMAX_PRIORITIES - 2, usb_device_stack,
                           &usb_device_taskdef);
}

#endif

//--------------------------------------------------------------------+
// Board API
//--------------------------------------------------------------------+

void board_init(void) {
// Peripheral control through I2C Expander
#if defined(TCA9554_ADDR) || defined(AW9523_ADDR)
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

#if defined(TCA9554_ADDR)
  // Turn on PERI_POWER that is controlled by TC9554 I2C Expander
  i2c_cmd_handle_t cmd = i2c_cmd_link_create();
  i2c_master_start(cmd);
  i2c_master_write_byte(cmd, TCA9554_ADDR << 1 | I2C_MASTER_WRITE, true);
  i2c_master_write_byte(cmd, TCA9554_CONFIGURATION_REG, true);
  i2c_master_write_byte(cmd, TCA9554_DEFAULT_CONFIG, true);
  i2c_master_stop(cmd);
  i2c_master_cmd_begin(i2c_num, cmd, 1000 / portTICK_PERIOD_MS);
  i2c_cmd_link_delete(cmd);
  vTaskDelay(30 / portTICK_PERIOD_MS);
  cmd = i2c_cmd_link_create();
  i2c_master_start(cmd);
  i2c_master_write_byte(cmd, TCA9554_ADDR << 1 | I2C_MASTER_WRITE, true);
  i2c_master_write_byte(cmd, TCA9554_OUTPUT_PORT_REG, true);
  i2c_master_write_byte(cmd, TCA9554_DEFAULT_VALUE, true);
  i2c_master_stop(cmd);
  i2c_master_cmd_begin(i2c_num, cmd, 1000 / portTICK_PERIOD_MS);
  i2c_cmd_link_delete(cmd);
#endif

#if defined(AW9523_ADDR)
  i2c_cmd_handle_t cmd = i2c_cmd_link_create();
  i2c_master_start(cmd);
  i2c_master_write_byte(cmd, AW9523_ADDR << 1 | I2C_MASTER_WRITE, true);
  i2c_master_write_byte(cmd, AW9523_REG_SOFTRESET, true);
  i2c_master_write_byte(cmd, 0, true);
  i2c_master_stop(cmd);
  i2c_master_cmd_begin(i2c_num, cmd, 1000 / portTICK_PERIOD_MS);
  i2c_cmd_link_delete(cmd);

  cmd = i2c_cmd_link_create();
  i2c_master_start(cmd);
  i2c_master_write_byte(cmd, AW9523_ADDR << 1 | I2C_MASTER_WRITE, true);
  i2c_master_write_byte(cmd, AW9523_REG_CONFIG0, true);
  i2c_master_write_byte(cmd, AW9523_DEFAULT_CONFIG >> 8, true);
  i2c_master_write_byte(cmd, AW9523_DEFAULT_CONFIG & 0xff, true);
  i2c_master_stop(cmd);
  i2c_master_cmd_begin(i2c_num, cmd, 1000 / portTICK_PERIOD_MS);
  i2c_cmd_link_delete(cmd);

  cmd = i2c_cmd_link_create();
  i2c_master_start(cmd);
  i2c_master_write_byte(cmd, AW9523_ADDR << 1 | I2C_MASTER_WRITE, true);
  i2c_master_write_byte(cmd, AW9523_REG_OUTPUT0, true);
  i2c_master_write_byte(cmd, AW9523_DEFAULT_OUTPUT >> 8, true);
  i2c_master_write_byte(cmd, AW9523_DEFAULT_OUTPUT & 0xff, true);
  i2c_master_stop(cmd);
  i2c_master_cmd_begin(i2c_num, cmd, 1000 / portTICK_PERIOD_MS);
  i2c_cmd_link_delete(cmd);
#endif

  i2c_driver_delete(i2c_num);
#endif // TCA9554_ADDR, AW9523_ADDR

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
  led_strip_rmt_config_t rmt_config = {
      .clk_src = RMT_CLK_SRC_DEFAULT, // different clock source can lead to different power consumption
      .resolution_hz = 10 * 1000 * 1000,  // RMT counter clock frequency, default = 10 Mhz
      .flags.with_dma = false,        // DMA feature is available on ESP target like ESP32-S3
  };

  led_strip_config_t strip_config = {
      .strip_gpio_num = NEOPIXEL_PIN,           // The GPIO that connected to the LED strip's data line
      .max_leds = NEOPIXEL_NUMBER,              // The number of LEDs in the strip,
      .led_pixel_format = LED_PIXEL_FORMAT_GRB, // Pixel format of your LED strip
      .led_model = LED_MODEL_WS2812,            // LED strip model
      .flags.invert_out = false,                // whether to invert the output signal
  };

  ESP_ERROR_CHECK(led_strip_new_rmt_device(&strip_config, &rmt_config, &led_strip));

  led_strip_clear(led_strip); // off
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

static usb_phy_handle_t phy_hdl;
void board_dfu_init(void) {
  // Configure USB PHY
  usb_phy_config_t phy_conf = {
    .controller = USB_PHY_CTRL_OTG,
    .target = USB_PHY_TARGET_INT,
    .otg_mode = USB_OTG_MODE_DEVICE,
    // https://github.com/hathach/tinyusb/issues/2943#issuecomment-2601888322
    // Set speed to undefined (auto-detect) to avoid timinng/racing issue with S3 with host such as macOS
    .otg_speed = USB_PHY_SPEED_UNDEFINED,
  };

  usb_new_phy(&phy_conf, &phy_hdl);
}

void board_reset(void) {
  esp_restart();
}

void board_dfu_complete(void) {
  // Set partition OTA0 as bootable and reset
  esp_ota_set_boot_partition(esp_partition_find_first(ESP_PARTITION_TYPE_APP, ESP_PARTITION_SUBTYPE_APP_OTA_0, NULL));
  esp_restart();
}

bool board_app_valid(void) {
  // esp32s2 is always enter DFU mode
  return false;
}

void board_app_jump(void) {
  // nothing to do
}

uint8_t board_usb_get_serial(uint8_t serial_id[16]) {
  // use factory default MAC as serial ID
  esp_efuse_mac_get_default(serial_id);
  return 6;
}

void board_led_write(uint32_t value) {
  (void) value;

#ifdef LED_PIN
  ledc_set_duty(ledc_channel.speed_mode, ledc_channel.channel, value);
  ledc_update_duty(ledc_channel.speed_mode, ledc_channel.channel);
#endif
}

void board_rgb_write(uint8_t const rgb[]) {
#ifdef NEOPIXEL_PIN
  uint32_t const r = (rgb[0] * NEOPIXEL_BRIGHTNESS) >> 8;
  uint32_t const g = (rgb[1] * NEOPIXEL_BRIGHTNESS) >> 8;
  uint32_t const b = (rgb[2] * NEOPIXEL_BRIGHTNESS) >> 8;

  for (uint32_t i = 0; i < NEOPIXEL_NUMBER; i++) {
    led_strip_set_pixel(led_strip, i, r, g, b);
  }
  led_strip_refresh(led_strip);
#endif

#ifdef DOTSTAR_PIN_DATA
  dotstar_write(rgb);
#endif
}

//--------------------------------------------------------------------+
// Timer
//--------------------------------------------------------------------+

static void internal_timer_cb(void* arg) {
  (void) arg;
  board_timer_handler();
}

void board_timer_start(uint32_t ms) {
  esp_timer_stop(timer_hdl);
  esp_timer_start_periodic(timer_hdl, ms * 1000);
}

void board_timer_stop(void) {
  esp_timer_stop(timer_hdl);
}

//--------------------------------------------------------------------+
// CDC Touch1200
//--------------------------------------------------------------------+
#ifndef BUILD_NO_TINYUSB

#if CONFIG_IDF_TARGET_ESP32S3
#include "hal/usb_serial_jtag_ll.h"

static void hw_cdc_reset_handler(void *arg) {
  portBASE_TYPE xTaskWoken = 0;
  uint32_t usbjtag_intr_status = usb_serial_jtag_ll_get_intsts_mask();
  usb_serial_jtag_ll_clr_intsts_mask(usbjtag_intr_status);

  if (usbjtag_intr_status & USB_SERIAL_JTAG_INTR_BUS_RESET) {
    xSemaphoreGiveFromISR((SemaphoreHandle_t)arg, &xTaskWoken);
  }

  if (xTaskWoken == pdTRUE) {
    portYIELD_FROM_ISR();
  }
}

static void usb_switch_to_cdc_jtag(void) {
  // Disable USB-OTG
  periph_module_reset(PERIPH_USB_MODULE);
  periph_module_disable(PERIPH_USB_MODULE);

  // Switch to hardware CDC+JTAG
  CLEAR_PERI_REG_MASK(RTC_CNTL_USB_CONF_REG,
                      (RTC_CNTL_SW_HW_USB_PHY_SEL | RTC_CNTL_SW_USB_PHY_SEL | RTC_CNTL_USB_PAD_ENABLE));

  // Do not use external PHY
  CLEAR_PERI_REG_MASK(USB_SERIAL_JTAG_CONF0_REG, USB_SERIAL_JTAG_PHY_SEL);

  // Release GPIO pins from  CDC+JTAG
  CLEAR_PERI_REG_MASK(USB_SERIAL_JTAG_CONF0_REG, USB_SERIAL_JTAG_USB_PAD_ENABLE);

  // Force the host to re-enumerate (BUS_RESET)
  gpio_config_t dp_dm_conf = {
      .pin_bit_mask = (1ULL << USBPHY_DM_NUM) | (1ULL < USBPHY_DP_NUM),
      .mode = GPIO_MODE_OUTPUT_OD,
      .pull_up_en = GPIO_PULLUP_DISABLE,
      .pull_down_en = GPIO_PULLDOWN_DISABLE,
      .intr_type = GPIO_INTR_DISABLE
  };
  gpio_config(&dp_dm_conf);
  gpio_set_level((gpio_num_t)USBPHY_DM_NUM, 0);
  gpio_set_level((gpio_num_t)USBPHY_DP_NUM, 0);

  // Initialize CDC+JTAG ISR to listen for BUS_RESET
  usb_serial_jtag_ll_phy_enable_external(false);
  usb_serial_jtag_ll_disable_intr_mask(USB_SERIAL_JTAG_LL_INTR_MASK);
  usb_serial_jtag_ll_clr_intsts_mask(USB_SERIAL_JTAG_LL_INTR_MASK);
  usb_serial_jtag_ll_ena_intr_mask(USB_SERIAL_JTAG_INTR_BUS_RESET);
  intr_handle_t intr_handle = NULL;
  SemaphoreHandle_t reset_sem = xSemaphoreCreateBinary();
  if (reset_sem) {
    if (esp_intr_alloc(ETS_USB_SERIAL_JTAG_INTR_SOURCE, 0, hw_cdc_reset_handler, reset_sem, &intr_handle) != ESP_OK) {
      vSemaphoreDelete(reset_sem);
      reset_sem = NULL;
      //log_e("HW USB CDC failed to init interrupts");
    }
  } else {
    //log_e("reset_sem init failed");
  }

  // Connect GPIOs to integrated CDC+JTAG
  SET_PERI_REG_MASK(USB_SERIAL_JTAG_CONF0_REG, USB_SERIAL_JTAG_USB_PAD_ENABLE);

  // Wait for BUS_RESET to give us back the semaphore
  if (reset_sem) {
    if (xSemaphoreTake(reset_sem, 1000 / portTICK_PERIOD_MS) != pdPASS) {
      //log_e("reset_sem timeout");
    }
    usb_serial_jtag_ll_disable_intr_mask(USB_SERIAL_JTAG_LL_INTR_MASK);
    esp_intr_free(intr_handle);
    vSemaphoreDelete(reset_sem);
  }
}
#endif

// Copied from Arduino's esp32-hal-tinyusb.c with usb_persist_mode = RESTART_BOOTLOADER, and usb_persist_enabled = false
static void IRAM_ATTR usb_persist_shutdown_handler(void) {
  // USB CDC Download: RESTART_BOOTLOADER
#if CONFIG_IDF_TARGET_ESP32S2
  periph_module_reset(PERIPH_USB_MODULE);
  periph_module_enable(PERIPH_USB_MODULE);
#endif

  REG_WRITE(RTC_CNTL_OPTION1_REG, RTC_CNTL_FORCE_DOWNLOAD_BOOT);
}

// Invoked when cdc when line state changed e.g connected/disconnected
// Use to reset to bootrom when disconnect with 1200 bps
void tud_cdc_line_state_cb(uint8_t instance, bool dtr, bool rts) {
  (void) rts;

  // DTR = false is counted as disconnected
  if (!dtr) {
    cdc_line_coding_t coding;
    tud_cdc_get_line_coding(&coding);

    if (coding.bit_rate == 1200) {
      printf("Touch1200: Reset to bootrom\n");
      // copied from Arduino's usb_persist_restart()
      esp_register_shutdown_handler(usb_persist_shutdown_handler);
#if CONFIG_IDF_TARGET_ESP32S3
      // Switch to JTAG since S3 bootrom has issue with uploading with USB OTG
      // https://github.com/espressif/arduino-esp32/issues/6762#issuecomment-1128621518
      usb_switch_to_cdc_jtag();
#endif
      esp_restart();
    }
  }
}
#endif

//--------------------------------------------------------------------+
// Display
//--------------------------------------------------------------------+

#ifdef DISPLAY_PIN_SCK

#define LCD_SPI   SPI2_HOST

spi_device_handle_t _display_spi;

void board_display_init(void) {
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

void board_display_draw_line(int y, uint16_t* pixel_color, uint32_t pixel_num) {
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

void dotstar_init(void) {
#ifdef DOTSTAR_PIN_PWR
  gpio_reset_pin(DOTSTAR_PIN_PWR);
  gpio_set_direction(DOTSTAR_PIN_PWR, GPIO_MODE_OUTPUT);
  gpio_set_level(DOTSTAR_PIN_PWR, DOTSTAR_POWER_STATE);
#endif

  spi_bus_config_t bus_cfg = {
    .miso_io_num     = -1,
    .mosi_io_num     = DOTSTAR_PIN_DATA,
    .sclk_io_num     = DOTSTAR_PIN_SCK,
    .quadwp_io_num   = -1,
    .quadhd_io_num   = -1,
    .max_transfer_sz = sizeof(_dotstar_data)
  };

  spi_device_interface_config_t devcfg = {
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

void dotstar_write(uint8_t const rgb[]) {
  // convert from 0-255 (8 bit) to 0-31 (5 bit)
  uint8_t const ds_brightness = (DOTSTAR_BRIGHTNESS * 32) / 256;

  // start frame
  _dotstar_data[0] = _dotstar_data[1] = _dotstar_data[2] = _dotstar_data[3] = 0;

  uint8_t* color = _dotstar_data+4;

  for(uint8_t i=0; i<DOTSTAR_NUMBER; i++) {
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

  static spi_transaction_t xact = {
    .length    = (sizeof(_dotstar_data) - 4 + (DOTSTAR_NUMBER+15)/16 )*8, // length in bits, see end frame not above
    .tx_buffer = _dotstar_data
  };

  spi_device_queue_trans(_dotstar_spi, &xact, portMAX_DELAY);
}

#endif
