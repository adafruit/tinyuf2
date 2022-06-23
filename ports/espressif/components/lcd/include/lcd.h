// Copyright 2019 Espressif Systems (Shanghai) PTE LTD
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
#pragma once

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include "esp_err.h"
#include "esp_log.h"
#include "driver/spi_master.h"

#define LCD_HOST    SPI2_HOST
#define DMA_CHAN    LCD_HOST

/*!< To speed up transfers, every SPI transfer sends a bunch of lines. This define specifies how many. More means more memory use, */
/*!< but less overhead for setting up / finishing transfers. Make sure 240 is dividable by this. */
#define PARALLEL_LINES 1

/*!< The LCD needs a bunch of command/argument values to be initialized. They are stored in this struct. */
typedef struct {
    uint8_t cmd;
    uint8_t data[16];
    uint8_t databytes; /*!< No of data in data; bit 7 = delay after set; 0xFF = end of cmds. */
} lcd_init_cmd_t;

typedef enum {
    LCD_TYPE_ILI = 1,
    LCD_TYPE_ST,
    LCD_TYPE_MAX,
} type_lcd_t;

/**
 * @brief This function is called (in irq context!) just before a transmission starts. It will
 * set the D/C line to the value indicated in the user field. 
 *
 * @param t The parameters required for this callback function.
 */
void lcd_spi_pre_transfer_callback(spi_transaction_t *t);

/**
 * @brief Initialize the display.
 *
 * @param spi Initialize the relevant parameters based on the given device handle.
 */
esp_err_t lcd_init(spi_device_handle_t spi);

void lcd_draw_lines(spi_device_handle_t spi, int ypos, uint16_t *linedata);

#ifdef __cplusplus
}
#endif
