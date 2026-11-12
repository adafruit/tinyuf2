
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

#ifdef CONFIG_XPOWERS_CHIP_AXP2102

#define XPOWERS_CHIP_AXP2102
#include "XPowersLib.h"
static const char *TAG = "AXP2101";

static XPowersPMU PMU;

#endif /* CONFIG_XPOWERS_CHIP_AXP2102 */

#define I2C_MASTER_NUM                  I2C_NUM_1
#define I2C_MASTER_FREQ_HZ              100000 /*!< I2C master clock frequency */
#define I2C_MASTER_SDA_IO               (gpio_num_t) 8
#define I2C_MASTER_SCL_IO               (gpio_num_t) 9

#define I2C_MASTER_TIMEOUT_MS           1000

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

static i2c_master_bus_handle_t pmu_bus;

// a device per call: the callbacks also get addresses other than the PMU's
static i2c_master_dev_handle_t pmu_device_add(uint8_t devAddr)
{
    i2c_device_config_t dev_config;
    memset(&dev_config, 0, sizeof(dev_config));
    dev_config.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    dev_config.device_address = devAddr;
    dev_config.scl_speed_hz = I2C_MASTER_FREQ_HZ;
    i2c_master_dev_handle_t dev;
    return i2c_master_bus_add_device(pmu_bus, &dev_config, &dev) == ESP_OK ? dev : NULL;
}

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
    i2c_master_dev_handle_t dev = pmu_device_add(devAddr);
    if (dev == NULL) {
        return ESP_FAIL;
    }
    // register write and data read are separate transactions, STOP between them
    esp_err_t ret = i2c_master_transmit(dev, &regAddr, 1, I2C_MASTER_TIMEOUT_MS);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "PMU i2c_master_transmit FAILED! > ");
    } else if ((ret = i2c_master_receive(dev, data, len, I2C_MASTER_TIMEOUT_MS)) != ESP_OK) {
        ESP_LOGE(TAG, "PMU READ FAILED! > ");
    }
    i2c_master_bus_rm_device(dev);
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
    i2c_master_dev_handle_t dev = pmu_device_add(devAddr);
    if (dev == NULL) {
        return ESP_FAIL;
    }
    i2c_master_transmit_multi_buffer_info_t buffers[] = {
        { .write_buffer = &regAddr, .buffer_size = 1 },
        { .write_buffer = data, .buffer_size = len },
    };
    esp_err_t ret = i2c_master_multi_buffer_transmit(dev, buffers, 2, I2C_MASTER_TIMEOUT_MS);
    i2c_master_bus_rm_device(dev);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "PMU WRITE FAILED! < ");
    }
    return ret == ESP_OK ? 0 : -1;
}

extern "C" bool board_init_extension()
{
  SSD1306_t dev;

  pmu_bus = i2c_bus_new(I2C_MASTER_NUM, I2C_MASTER_SDA_IO, I2C_MASTER_SCL_IO);

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

    PMU.setDC1Voltage(3300); // WROOM, OLED
    PMU.enableDC1();

    PMU.setDC3Voltage(3400);   // V2.0 - SA868, NeoPixel
    PMU.enableDC3();

    // Rev2.1 pixel light and ESP have the same power supply
    // PMU.setALDO3Voltage(3300); // V2.1 - SA868 .No need to turn it on here
    // PMU.enableALDO3();

    /* no power for GNSS and/or Mic at this moment */

    // uSD
    PMU.setALDO2Voltage(3300);
    PMU.enableALDO2();

    // use X axis offset for SH1106 OLED
    dev._offset = CONFIG_OFFSETX;

  } else {
    ESP_LOGE(TAG, "Init PMU FAILED!");

    // use no offset with SSD1306 OLED
    dev._offset = 0;
  }

  // Check the OLED device address. Rev2.1 has two I2C device addresses, which are used to distinguish VHF or UHF.
  uint8_t oled_addr = 0x3C;
  uint8_t data[1];
  if (pmu_register_read(0x3C,0x00,data,1) == 0){
    ESP_LOGI(tag, "Find OLED address is 0x3C");
    oled_addr = 0x3C;
  }else if (pmu_register_read(0x3D,0x00,data,1) == 0){
    ESP_LOGI(tag, "Find OLED address is 0x3D");
    oled_addr = 0x3D;
  }

#if CONFIG_I2C_INTERFACE
  i2c_master_init(&dev, pmu_bus, -1, oled_addr);
#endif // CONFIG_I2C_INTERFACE

#if CONFIG_FLIP
  dev._flip = true;
  ESP_LOGW(tag, "Flip upside down");
#endif

  ESP_LOGI(tag, "Panel is 128x64");
  ssd1306_init(&dev, 128, 64);

  ssd1306_clear_screen(&dev, false);
  ssd1306_contrast(&dev, 0xff);

  ssd1306_display_text(&dev, 1, " T-TWR Plus Boot", 16, true);
  ssd1306_display_text(&dev, 4, "Put UF2 firmware", 16, false);
  ssd1306_display_text(&dev, 6, "on " UF2_VOLUME_LABEL " Vol", 16, false);

  //ssd1306_clear_line(&dev, 5, false);

  return true;
}
