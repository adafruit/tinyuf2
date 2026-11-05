#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "driver/i2c_master.h"
#include "driver/gpio.h"
#include "esp_log.h"

#include "ssd1306.h"

#define tag "SSD1306"

//#define I2C_MASTER_FREQ_HZ 400000 /*!< I2C master clock frequency. no higher than 1MHz for now */
#define I2C_MASTER_FREQ_HZ 800000 /*!< I2C master clock frequency. no higher than 1MHz for now */
//#define I2C_MASTER_FREQ_HZ 1000000 /*!< I2C master clock frequency. no higher than 1MHz for now */
#define I2C_TIMEOUT_MS 10

void i2c_master_init(SSD1306_t * dev, i2c_master_bus_handle_t bus, int16_t reset, int address)
{
	i2c_device_config_t dev_config = {
		.dev_addr_length = I2C_ADDR_BIT_LEN_7,
		.device_address = address,
		.scl_speed_hz = I2C_MASTER_FREQ_HZ
	};
	ESP_ERROR_CHECK(i2c_master_bus_add_device(bus, &dev_config, &dev->_i2c_dev));

	if (reset >= 0) {
		//gpio_pad_select_gpio(reset);
		gpio_reset_pin(reset);
		gpio_set_direction(reset, GPIO_MODE_OUTPUT);
		gpio_set_level(reset, 0);
		vTaskDelay(50 / portTICK_PERIOD_MS);
		gpio_set_level(reset, 1);
	}
	dev->_address = address;
	dev->_flip = false;
}

void i2c_init(SSD1306_t * dev, int width, int height) {
	dev->_width = width;
	dev->_height = height;
	dev->_pages = 8;
	if (dev->_height == 32) dev->_pages = 4;

	uint8_t cmd[32];
	size_t n = 0;

	cmd[n++] = OLED_CONTROL_BYTE_CMD_STREAM;
	cmd[n++] = OLED_CMD_DISPLAY_OFF;				// AE
	cmd[n++] = OLED_CMD_SET_MUX_RATIO;			// A8
	if (dev->_height == 64) cmd[n++] = 0x3F;
	if (dev->_height == 32) cmd[n++] = 0x1F;
	cmd[n++] = OLED_CMD_SET_DISPLAY_OFFSET;		// D3
	cmd[n++] = 0x00;
	//cmd[n++] = OLED_CONTROL_BYTE_DATA_STREAM;	// 40
	cmd[n++] = OLED_CMD_SET_DISPLAY_START_LINE;	// 40
	//cmd[n++] = OLED_CMD_SET_SEGMENT_REMAP;		// A1
	if (dev->_flip) {
		cmd[n++] = OLED_CMD_SET_SEGMENT_REMAP_0;		// A0
	} else {
		cmd[n++] = OLED_CMD_SET_SEGMENT_REMAP_1;		// A1
	}
	cmd[n++] = OLED_CMD_SET_COM_SCAN_MODE;		// C8
	cmd[n++] = OLED_CMD_SET_DISPLAY_CLK_DIV;		// D5
	cmd[n++] = 0x80;
	cmd[n++] = OLED_CMD_SET_COM_PIN_MAP;			// DA
	if (dev->_height == 64) cmd[n++] = 0x12;
	if (dev->_height == 32) cmd[n++] = 0x02;
	cmd[n++] = OLED_CMD_SET_CONTRAST;			// 81
	cmd[n++] = 0xFF;
	cmd[n++] = OLED_CMD_DISPLAY_RAM;				// A4
	cmd[n++] = OLED_CMD_SET_VCOMH_DESELCT;		// DB
	cmd[n++] = 0x40;
	cmd[n++] = OLED_CMD_SET_MEMORY_ADDR_MODE;	// 20
	//cmd[n++] = OLED_CMD_SET_HORI_ADDR_MODE;	// 00
	cmd[n++] = OLED_CMD_SET_PAGE_ADDR_MODE;		// 02
	// Set Lower Column Start Address for Page Addressing Mode
	cmd[n++] = 0x00;
	// Set Higher Column Start Address for Page Addressing Mode
	cmd[n++] = 0x10;
	cmd[n++] = OLED_CMD_SET_CHARGE_PUMP;			// 8D
	cmd[n++] = 0x14;
	cmd[n++] = OLED_CMD_DEACTIVE_SCROLL;			// 2E
	cmd[n++] = OLED_CMD_DISPLAY_NORMAL;			// A6
	cmd[n++] = OLED_CMD_DISPLAY_ON;				// AF

	esp_err_t espRc = i2c_master_transmit(dev->_i2c_dev, cmd, n, I2C_TIMEOUT_MS);
	if (espRc == ESP_OK) {
		ESP_LOGI(tag, "OLED configured successfully");
	} else {
		ESP_LOGE(tag, "OLED configuration failed. code: 0x%.2X", espRc);
	}
}


void i2c_display_image(SSD1306_t * dev, int page, int seg, uint8_t * images, int width) {
	if (page >= dev->_pages) return;
	if (seg >= dev->_width) return;

	int _seg = seg + dev->_offset; // CONFIG_OFFSETX;
	uint8_t columLow = _seg & 0x0F;
	uint8_t columHigh = (_seg >> 4) & 0x0F;

	int _page = page;
	if (dev->_flip) {
		_page = (dev->_pages - page) - 1;
	}

	uint8_t cmd[] = {
		OLED_CONTROL_BYTE_CMD_STREAM,
		// Set Lower Column Start Address for Page Addressing Mode
		0x00 + columLow,
		// Set Higher Column Start Address for Page Addressing Mode
		0x10 + columHigh,
		// Set Page Start Address for Page Addressing Mode
		0xB0 | _page
	};
	i2c_master_transmit(dev->_i2c_dev, cmd, sizeof(cmd), I2C_TIMEOUT_MS);

	uint8_t data_stream = OLED_CONTROL_BYTE_DATA_STREAM;
	i2c_master_transmit_multi_buffer_info_t data[] = {
		{ .write_buffer = &data_stream, .buffer_size = 1 },
		{ .write_buffer = images, .buffer_size = width }
	};
	i2c_master_multi_buffer_transmit(dev->_i2c_dev, data, 2, I2C_TIMEOUT_MS);
}

void i2c_contrast(SSD1306_t * dev, int contrast) {
	int _contrast = contrast;
	if (contrast < 0x0) _contrast = 0;
	if (contrast > 0xFF) _contrast = 0xFF;

	uint8_t cmd[] = {
		OLED_CONTROL_BYTE_CMD_STREAM,
		OLED_CMD_SET_CONTRAST,			// 81
		_contrast
	};
	i2c_master_transmit(dev->_i2c_dev, cmd, sizeof(cmd), I2C_TIMEOUT_MS);
}


void i2c_hardware_scroll(SSD1306_t * dev, ssd1306_scroll_type_t scroll) {
	esp_err_t espRc;
	uint8_t cmd[16];
	size_t n = 0;

	cmd[n++] = OLED_CONTROL_BYTE_CMD_STREAM;

	if (scroll == SCROLL_RIGHT) {
		cmd[n++] = OLED_CMD_HORIZONTAL_RIGHT;	// 26
		cmd[n++] = 0x00; // Dummy byte
		cmd[n++] = 0x00; // Define start page address
		cmd[n++] = 0x07; // Frame frequency
		cmd[n++] = 0x07; // Define end page address
		cmd[n++] = 0x00; //
		cmd[n++] = 0xFF; //
		cmd[n++] = OLED_CMD_ACTIVE_SCROLL;		// 2F
	}

	if (scroll == SCROLL_LEFT) {
		cmd[n++] = OLED_CMD_HORIZONTAL_LEFT;		// 27
		cmd[n++] = 0x00; // Dummy byte
		cmd[n++] = 0x00; // Define start page address
		cmd[n++] = 0x07; // Frame frequency
		cmd[n++] = 0x07; // Define end page address
		cmd[n++] = 0x00; //
		cmd[n++] = 0xFF; //
		cmd[n++] = OLED_CMD_ACTIVE_SCROLL;		// 2F
	}

	if (scroll == SCROLL_DOWN) {
		cmd[n++] = OLED_CMD_CONTINUOUS_SCROLL;	// 29
		cmd[n++] = 0x00; // Dummy byte
		cmd[n++] = 0x00; // Define start page address
		cmd[n++] = 0x07; // Frame frequency
		//cmd[n++] = 0x01; // Define end page address
		cmd[n++] = 0x00; // Define end page address
		cmd[n++] = 0x3F; // Vertical scrolling offset

		cmd[n++] = OLED_CMD_VERTICAL;			// A3
		cmd[n++] = 0x00;
		if (dev->_height == 64)
		//cmd[n++] = 0x7F;
		cmd[n++] = 0x40;
		if (dev->_height == 32)
		cmd[n++] = 0x20;
		cmd[n++] = OLED_CMD_ACTIVE_SCROLL;		// 2F
	}

	if (scroll == SCROLL_UP) {
		cmd[n++] = OLED_CMD_CONTINUOUS_SCROLL;	// 29
		cmd[n++] = 0x00; // Dummy byte
		cmd[n++] = 0x00; // Define start page address
		cmd[n++] = 0x07; // Frame frequency
		//cmd[n++] = 0x01; // Define end page address
		cmd[n++] = 0x00; // Define end page address
		cmd[n++] = 0x01; // Vertical scrolling offset

		cmd[n++] = OLED_CMD_VERTICAL;			// A3
		cmd[n++] = 0x00;
		if (dev->_height == 64)
		//cmd[n++] = 0x7F;
		cmd[n++] = 0x40;
		if (dev->_height == 32)
		cmd[n++] = 0x20;
		cmd[n++] = OLED_CMD_ACTIVE_SCROLL;		// 2F
	}

	if (scroll == SCROLL_STOP) {
		cmd[n++] = OLED_CMD_DEACTIVE_SCROLL;		// 2E
	}

	espRc = i2c_master_transmit(dev->_i2c_dev, cmd, n, I2C_TIMEOUT_MS);
	if (espRc == ESP_OK) {
		ESP_LOGD(tag, "Scroll command succeeded");
	} else {
		ESP_LOGE(tag, "Scroll command failed. code: 0x%.2X", espRc);
	}
}
