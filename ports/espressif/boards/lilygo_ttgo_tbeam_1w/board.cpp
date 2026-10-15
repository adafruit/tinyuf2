
#include <stdbool.h>
#include "board_api.h"


#if CONFIG_SSD1306_128x64
#include "esp_log.h"
#include "sdkconfig.h"
#include "driver/gpio.h"
#include "driver/i2c.h"


#include "ssd1306.h"
#include "font8x8_basic.h"

#define tag "SSD1306"
#endif

#define I2C_MASTER_NUM                  I2C_NUM_1
#define I2C_MASTER_FREQ_HZ              100000 /*!< I2C master clock frequency */
#define I2C_MASTER_SDA_IO               (gpio_num_t) 8
#define I2C_MASTER_SCL_IO               (gpio_num_t) 9


#define I2C_MASTER_TX_BUF_DISABLE       0                           /*!< I2C master doesn't need buffer */
#define I2C_MASTER_RX_BUF_DISABLE       0                           /*!< I2C master doesn't need buffer */
#define I2C_MASTER_TIMEOUT_MS           1000

#define WRITE_BIT                       I2C_MASTER_WRITE            /*!< I2C master write */
#define READ_BIT                        I2C_MASTER_READ             /*!< I2C master read */
#define ACK_CHECK_EN                    0x1                         /*!< I2C master will check ack from slave*/
#define ACK_CHECK_DIS                   0x0                         /*!< I2C master will not check ack from slave */
#define ACK_VAL                         (i2c_ack_type_t)0x0         /*!< I2C ack value */
#define NACK_VAL                        (i2c_ack_type_t)0x1         /*!< I2C nack value */

extern "C" bool board_init_extension()
{
  SSD1306_t dev;

  i2c_config_t i2c_conf ;
  memset(&i2c_conf, 0, sizeof(i2c_conf));
  i2c_conf.mode = I2C_MODE_MASTER;
  i2c_conf.sda_io_num = I2C_MASTER_SDA_IO;
  i2c_conf.scl_io_num = I2C_MASTER_SCL_IO;
  i2c_conf.sda_pullup_en = GPIO_PULLUP_ENABLE;
  i2c_conf.scl_pullup_en = GPIO_PULLUP_ENABLE;
  i2c_conf.master.clk_speed = I2C_MASTER_FREQ_HZ;
  i2c_param_config(I2C_MASTER_NUM, &i2c_conf);
  i2c_driver_install(I2C_MASTER_NUM, i2c_conf.mode,
                     I2C_MASTER_RX_BUF_DISABLE, I2C_MASTER_TX_BUF_DISABLE, 0);

  // use X axis offset for SH1106 OLED
  dev._offset = CONFIG_OFFSETX;

#if CONFIG_I2C_INTERFACE
  i2c_master_init(&dev, I2C_MASTER_SDA_IO, I2C_MASTER_SCL_IO, CONFIG_RESET_GPIO, 0x3C);
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
