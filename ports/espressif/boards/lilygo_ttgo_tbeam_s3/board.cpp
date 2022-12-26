
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

#ifdef CONFIG_XPOWERS_CHIP_AXP2102

#define XPOWERS_CHIP_AXP2102
#include "XPowersLib.h"
static const char *TAG = "AXP2101";

static XPowersPMU PMU;

#endif /* CONFIG_XPOWERS_CHIP_AXP2102 */


#define I2C_MASTER_NUM                  CONFIG_I2C_MASTER_PORT_NUM
#define I2C_MASTER_FREQ_HZ              CONFIG_I2C_MASTER_FREQUENCY /*!< I2C master clock frequency */
#define I2C_MASTER_SDA_IO               (gpio_num_t)CONFIG_PMU_I2C_SDA
#define I2C_MASTER_SCL_IO               (gpio_num_t)CONFIG_PMU_I2C_SCL


#define I2C_MASTER_TX_BUF_DISABLE       0                           /*!< I2C master doesn't need buffer */
#define I2C_MASTER_RX_BUF_DISABLE       0                           /*!< I2C master doesn't need buffer */
#define I2C_MASTER_TIMEOUT_MS           1000

#define WRITE_BIT                       I2C_MASTER_WRITE            /*!< I2C master write */
#define READ_BIT                        I2C_MASTER_READ             /*!< I2C master read */
#define ACK_CHECK_EN                    0x1                         /*!< I2C master will check ack from slave*/
#define ACK_CHECK_DIS                   0x0                         /*!< I2C master will not check ack from slave */
#define ACK_VAL                         (i2c_ack_type_t)0x0         /*!< I2C ack value */
#define NACK_VAL                        (i2c_ack_type_t)0x1         /*!< I2C nack value */

/**
 * @brief Read a sequence of bytes from a pmu registers
 */
int pmu_register_read(uint8_t devAddr, uint8_t regAddr, uint8_t *data, uint8_t len)
{
    if (len == 0) {
        return ESP_OK;
    }
    if (data == NULL) {
        return ESP_FAIL;
    }
    i2c_cmd_handle_t cmd;

    cmd = i2c_cmd_link_create();
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (devAddr << 1) | WRITE_BIT, ACK_CHECK_EN);
    i2c_master_write_byte(cmd, regAddr, ACK_CHECK_EN);
    i2c_master_stop(cmd);
    esp_err_t ret =  i2c_master_cmd_begin(I2C_MASTER_NUM, cmd, 1000 / portTICK_RATE_MS);
    i2c_cmd_link_delete(cmd);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "PMU i2c_master_cmd_begin FAILED! > ");
        return ESP_FAIL;
    }
    cmd = i2c_cmd_link_create();
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (devAddr << 1) | READ_BIT, ACK_CHECK_EN);
    if (len > 1) {
        i2c_master_read(cmd, data, len - 1, ACK_VAL);
    }
    i2c_master_read_byte(cmd, &data[len - 1], NACK_VAL);
    i2c_master_stop(cmd);
    ret = i2c_master_cmd_begin(I2C_MASTER_NUM, cmd, 1000 / portTICK_RATE_MS);
    i2c_cmd_link_delete(cmd);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "PMU READ FAILED! > ");
    }
    return ret == ESP_OK ? 0 : -1;
}

/**
 * @brief Write a byte to a pmu register
 */
int pmu_register_write_byte(uint8_t devAddr, uint8_t regAddr, uint8_t *data, uint8_t len)
{
    if (data == NULL) {
        return ESP_FAIL;
    }
    i2c_cmd_handle_t cmd = i2c_cmd_link_create();
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (devAddr << 1) |  I2C_MASTER_WRITE, ACK_CHECK_EN);
    i2c_master_write_byte(cmd, regAddr, ACK_CHECK_EN);
    i2c_master_write(cmd, data, len, ACK_CHECK_EN);
    i2c_master_stop(cmd);
    esp_err_t ret = i2c_master_cmd_begin(I2C_MASTER_NUM, cmd, 1000 / portTICK_RATE_MS);
    i2c_cmd_link_delete(cmd);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "PMU WRITE FAILED! < ");
    }
    return ret == ESP_OK ? 0 : -1;
}

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

  if (PMU.begin(AXP2101_SLAVE_ADDRESS, pmu_register_read, pmu_register_write_byte)) {

    ESP_LOGI(TAG, "Init PMU SUCCESS!");

    //Turn off not use power channel
    PMU.disableDC2();
    PMU.disableDC3();
    PMU.disableDC4();
    PMU.disableDC5();

    PMU.disableALDO1();
    PMU.disableALDO2();
    PMU.disableALDO3();
    PMU.disableALDO4();
    PMU.disableBLDO1();
    PMU.disableBLDO2();

    PMU.setDC1Voltage(3300);
    PMU.enableDC1();

    /* no power for LoRa and/or GNSS at this moment */

    // sensors, OLED
    PMU.setALDO1Voltage(3300);
    PMU.enableALDO1();

    // RTC
    PMU.setALDO2Voltage(3300);
    PMU.enableALDO2();

    // uSD
    PMU.setBLDO1Voltage(3300);
    PMU.enableBLDO1();

    // use X axis offset for SH1106 OLED
    dev._offset = CONFIG_OFFSETX;

  } else {
    ESP_LOGE(TAG, "Init PMU FAILED!");

    // use no offset with SSD1306 OLED
    dev._offset = 0;
  }

#if CONFIG_I2C_INTERFACE

  ESP_LOGI(tag, "INTERFACE is i2c");
  ESP_LOGI(tag, "CONFIG_SDA_GPIO=%d",CONFIG_SDA_GPIO);
  ESP_LOGI(tag, "CONFIG_SCL_GPIO=%d",CONFIG_SCL_GPIO);
  ESP_LOGI(tag, "CONFIG_RESET_GPIO=%d",CONFIG_RESET_GPIO);
  i2c_master_init(&dev, CONFIG_SDA_GPIO, CONFIG_SCL_GPIO, CONFIG_RESET_GPIO);
#endif // CONFIG_I2C_INTERFACE

#if CONFIG_FLIP
  dev._flip = true;
  ESP_LOGW(tag, "Flip upside down");
#endif

  ESP_LOGI(tag, "Panel is 128x64");
  ssd1306_init(&dev, 128, 64);

  ssd1306_clear_screen(&dev, false);
  ssd1306_contrast(&dev, 0xff);

  ssd1306_display_text(&dev, 1, "  T-Beam  Boot  ", 16, true);
  ssd1306_display_text(&dev, 4, "Put UF2 firmware", 16, false);
  ssd1306_display_text(&dev, 6, "on " UF2_VOLUME_LABEL " Vol", 16, false);

  //ssd1306_clear_line(&dev, 5, false);

  return true;
}

