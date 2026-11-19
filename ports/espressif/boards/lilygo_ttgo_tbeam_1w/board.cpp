
#include <stdbool.h>
#include "board_api.h"


#if CONFIG_SSD1306_128x64
#include "esp_log.h"
#include "sdkconfig.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"


#include "ssd1306.h"
#include "font8x8_basic.h"

#define tag "SSD1306"
#endif

#define I2C_MASTER_NUM                  I2C_NUM_1
#define I2C_MASTER_SDA_IO               (gpio_num_t) 8
#define I2C_MASTER_SCL_IO               (gpio_num_t) 9


static i2c_master_bus_handle_t i2c_bus_new(i2c_port_num_t port, gpio_num_t sda, gpio_num_t scl)
{
  i2c_master_bus_config_t bus_config;
  memset(&bus_config, 0, sizeof(bus_config));
  bus_config.i2c_port = port;
  bus_config.sda_io_num = sda;
  bus_config.scl_io_num = scl;
  bus_config.clk_source = I2C_CLK_SRC_DEFAULT;
  bus_config.glitch_ignore_cnt = 7;
  bus_config.flags.enable_internal_pullup = 1;
  i2c_master_bus_handle_t bus;
  ESP_ERROR_CHECK(i2c_new_master_bus(&bus_config, &bus));
  return bus;
}

extern "C" bool board_init_extension()
{
  SSD1306_t dev;

  // use X axis offset for SH1106 OLED
  dev._offset = CONFIG_OFFSETX;

#if CONFIG_I2C_INTERFACE
  i2c_master_init(&dev, i2c_bus_new(I2C_MASTER_NUM, I2C_MASTER_SDA_IO, I2C_MASTER_SCL_IO), CONFIG_RESET_GPIO, 0x3C);
#endif // CONFIG_I2C_INTERFACE

#if CONFIG_FLIP
  dev._flip = true;
  ESP_LOGW(tag, "Flip upside down");
#endif

  ESP_LOGI(tag, "Panel is 128x64");
  ssd1306_init(&dev, 128, 64);

  ssd1306_clear_screen(&dev, false);
  ssd1306_contrast(&dev, 0xff);

  ssd1306_display_text(&dev, 1, " T-Beam 1W Boot ", 16, true);
  ssd1306_display_text(&dev, 4, "Put UF2 firmware", 16, false);
  ssd1306_display_text(&dev, 6, "on " UF2_VOLUME_LABEL " Vol", 16, false);

  //ssd1306_clear_line(&dev, 5, false);

  return true;
}
