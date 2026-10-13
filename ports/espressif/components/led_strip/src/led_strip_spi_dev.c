/*
 * SPDX-FileCopyrightText: 2022-2025 Espressif Systems (Shanghai) CO LTD
 *
 * SPDX-License-Identifier: Apache-2.0
 */
#include <stdlib.h>
#include <string.h>
#include <sys/cdefs.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_check.h"
#include "esp_rom_gpio.h"
#include "esp_heap_caps.h"
#include "soc/spi_periph.h"
#include "led_strip.h"
#include "led_strip_interface.h"
#include "led_strip_common.h"

#define LED_STRIP_SPI_DEFAULT_RESOLUTION (2.5 * 1000 * 1000) // 2.5MHz resolution
#define LED_STRIP_SPI_WS2816_RESOLUTION (2.7 * 1000 * 1000)  // 2.7MHz resolution
#define LED_STRIP_SPI_DEFAULT_TRANS_QUEUE_SIZE 4

#define SPI_BYTES_PER_COLOR_BYTE 3
#define SPI_BITS_PER_COLOR_BYTE (SPI_BYTES_PER_COLOR_BYTE * 8)
#define SPI_TRANS_TIMEOUT portMAX_DELAY

static const char *TAG = "led_strip_spi";

typedef struct {
    led_strip_t base;
    spi_host_device_t spi_host;
    spi_device_handle_t spi_device;
    uint32_t strip_len;
    uint8_t bytes_per_pixel;
    led_color_component_format_t component_fmt;
    spi_transaction_t trans;
    led_strip_trans_state_atomic_t trans_state;
    uint8_t pixel_buf[];
} led_strip_spi_obj;

static esp_err_t led_strip_spi_trans(led_strip_spi_obj *spi_strip)
{
    memset(&spi_strip->trans, 0, sizeof(spi_strip->trans));
    spi_strip->trans.length = spi_strip->strip_len * spi_strip->bytes_per_pixel * SPI_BITS_PER_COLOR_BYTE;
    spi_strip->trans.tx_buffer = spi_strip->pixel_buf;
    spi_strip->trans.rx_buffer = NULL;
    return spi_device_queue_trans(spi_strip->spi_device, &spi_strip->trans, SPI_TRANS_TIMEOUT);
}

static esp_err_t led_strip_spi_wait_trans_done(led_strip_spi_obj *spi_strip)
{
    spi_transaction_t *tx_conf = NULL;
    ESP_RETURN_ON_ERROR(spi_device_get_trans_result(spi_strip->spi_device, &tx_conf, SPI_TRANS_TIMEOUT), TAG, "wait for SPI done failed");
    atomic_store(&spi_strip->trans_state, LED_STRIP_TRANS_IDLE);
    return ESP_OK;
}

// please make sure to zero-initialize the buf before calling this function
static void __led_strip_spi_bit(uint8_t data, uint8_t *buf)
{
    // Each color of 1 bit is represented by 3 bits of SPI, low_level:100 ,high_level:110
    // So a color byte occupies 3 bytes of SPI.
    *(buf + 2) |= data & BIT(0) ? BIT(2) | BIT(1) : BIT(2);
    *(buf + 2) |= data & BIT(1) ? BIT(5) | BIT(4) : BIT(5);
    *(buf + 2) |= data & BIT(2) ? BIT(7) : 0x00;
    *(buf + 1) |= BIT(0);
    *(buf + 1) |= data & BIT(3) ? BIT(3) | BIT(2) : BIT(3);
    *(buf + 1) |= data & BIT(4) ? BIT(6) | BIT(5) : BIT(6);
    *(buf + 0) |= data & BIT(5) ? BIT(1) | BIT(0) : BIT(1);
    *(buf + 0) |= data & BIT(6) ? BIT(4) | BIT(3) : BIT(4);
    *(buf + 0) |= data & BIT(7) ? BIT(7) | BIT(6) : BIT(7);
}

static esp_err_t led_strip_spi_set_pixel(led_strip_t *strip, uint32_t index, uint32_t red, uint32_t green, uint32_t blue)
{
    led_strip_spi_obj *spi_strip = __containerof(strip, led_strip_spi_obj, base);
    ESP_RETURN_ON_FALSE(index < spi_strip->strip_len, ESP_ERR_INVALID_ARG, TAG, "index out of maximum number of LEDs");
    ESP_RETURN_ON_FALSE(led_strip_trans_state_try_set(&spi_strip->trans_state, LED_STRIP_TRANS_IDLE, LED_STRIP_TRANS_LOCKED),
                        ESP_ERR_INVALID_STATE, TAG, "SPI transaction is busy");
    // 3 pixels take 72bits(9bytes)
    uint32_t start = index * spi_strip->bytes_per_pixel * SPI_BYTES_PER_COLOR_BYTE;
    uint8_t *pixel_buf = spi_strip->pixel_buf;
    struct format_layout format = spi_strip->component_fmt.format;
    memset(pixel_buf + start, 0, spi_strip->bytes_per_pixel * SPI_BYTES_PER_COLOR_BYTE);

    uint8_t pos_bytes = format.bytes_per_color;
    for (uint8_t i = 0; i < format.bytes_per_color; i++) {
        uint8_t color_shift = 8 * (format.bytes_per_color - 1 - i);
        __led_strip_spi_bit((red >> color_shift) & 0xFF, &pixel_buf[start + SPI_BYTES_PER_COLOR_BYTE * (format.r_pos * pos_bytes + i)]);
        __led_strip_spi_bit((green >> color_shift) & 0xFF, &pixel_buf[start + SPI_BYTES_PER_COLOR_BYTE * (format.g_pos * pos_bytes + i)]);
        __led_strip_spi_bit((blue >> color_shift) & 0xFF, &pixel_buf[start + SPI_BYTES_PER_COLOR_BYTE * (format.b_pos * pos_bytes + i)]);
        if (format.num_components > 3) {
            __led_strip_spi_bit(0, &pixel_buf[start + SPI_BYTES_PER_COLOR_BYTE * (format.w_pos * pos_bytes + i)]);
        }
    }
    atomic_store(&spi_strip->trans_state, LED_STRIP_TRANS_IDLE);
    return ESP_OK;
}

static esp_err_t led_strip_spi_set_pixel_rgbw(led_strip_t *strip, uint32_t index, uint32_t red, uint32_t green, uint32_t blue, uint32_t white)
{
    led_strip_spi_obj *spi_strip = __containerof(strip, led_strip_spi_obj, base);
    struct format_layout format = spi_strip->component_fmt.format;
    ESP_RETURN_ON_FALSE(index < spi_strip->strip_len, ESP_ERR_INVALID_ARG, TAG, "index out of maximum number of LEDs");
    ESP_RETURN_ON_FALSE(format.num_components == 4, ESP_ERR_INVALID_ARG, TAG, "led doesn't have 4 components");
    ESP_RETURN_ON_FALSE(led_strip_trans_state_try_set(&spi_strip->trans_state, LED_STRIP_TRANS_IDLE, LED_STRIP_TRANS_LOCKED),
                        ESP_ERR_INVALID_STATE, TAG, "SPI transaction is busy");

    // LED_PIXEL_FORMAT_GRBW takes 96bits(12bytes)
    uint32_t start = index * spi_strip->bytes_per_pixel * SPI_BYTES_PER_COLOR_BYTE;
    uint8_t *pixel_buf = spi_strip->pixel_buf;
    memset(pixel_buf + start, 0, spi_strip->bytes_per_pixel * SPI_BYTES_PER_COLOR_BYTE);

    uint8_t pos_bytes = format.bytes_per_color;
    for (uint8_t i = 0; i < format.bytes_per_color; i++) {
        uint8_t color_shift = 8 * (format.bytes_per_color - 1 - i);
        __led_strip_spi_bit((red >> color_shift) & 0xFF, &pixel_buf[start + SPI_BYTES_PER_COLOR_BYTE * (format.r_pos * pos_bytes + i)]);
        __led_strip_spi_bit((green >> color_shift) & 0xFF, &pixel_buf[start + SPI_BYTES_PER_COLOR_BYTE * (format.g_pos * pos_bytes + i)]);
        __led_strip_spi_bit((blue >> color_shift) & 0xFF, &pixel_buf[start + SPI_BYTES_PER_COLOR_BYTE * (format.b_pos * pos_bytes + i)]);
        __led_strip_spi_bit((white >> color_shift) & 0xFF, &pixel_buf[start + SPI_BYTES_PER_COLOR_BYTE * (format.w_pos * pos_bytes + i)]);
    }
    atomic_store(&spi_strip->trans_state, LED_STRIP_TRANS_IDLE);
    return ESP_OK;
}

static esp_err_t led_strip_spi_refresh_async(led_strip_t *strip)
{
    esp_err_t ret = ESP_OK;
    led_strip_spi_obj *spi_strip = __containerof(strip, led_strip_spi_obj, base);
    ESP_RETURN_ON_FALSE(led_strip_trans_state_try_set(&spi_strip->trans_state, LED_STRIP_TRANS_IDLE, LED_STRIP_TRANS_INFLIGHT),
                        ESP_ERR_INVALID_STATE, TAG, "SPI transaction is busy");
    ESP_GOTO_ON_ERROR(led_strip_spi_trans(spi_strip), err, TAG, "transmit pixels by SPI failed");
    return ret;
err:
    atomic_store(&spi_strip->trans_state, LED_STRIP_TRANS_IDLE);
    return ret;
}

static esp_err_t led_strip_spi_refresh_async_done(led_strip_t *strip)
{
    esp_err_t ret = ESP_OK;
    led_strip_spi_obj *spi_strip = __containerof(strip, led_strip_spi_obj, base);
    ESP_RETURN_ON_FALSE(led_strip_trans_state_try_set(&spi_strip->trans_state, LED_STRIP_TRANS_INFLIGHT, LED_STRIP_TRANS_LOCKED),
                        ESP_ERR_INVALID_STATE, TAG, "no async refresh in progress");
    ESP_GOTO_ON_ERROR(led_strip_spi_wait_trans_done(spi_strip), err, TAG, "wait for done failed");
    return ret;
err:
    atomic_store(&spi_strip->trans_state, LED_STRIP_TRANS_INFLIGHT);
    return ret;
}

static esp_err_t led_strip_spi_refresh(led_strip_t *strip)
{
    esp_err_t ret = ESP_OK;
    led_strip_spi_obj *spi_strip = __containerof(strip, led_strip_spi_obj, base);
    ESP_RETURN_ON_FALSE(led_strip_trans_state_try_set(&spi_strip->trans_state, LED_STRIP_TRANS_IDLE, LED_STRIP_TRANS_LOCKED),
                        ESP_ERR_INVALID_STATE, TAG, "SPI transaction is busy");
    ESP_GOTO_ON_ERROR(led_strip_spi_trans(spi_strip), err, TAG, "transmit pixels by SPI failed");
    ESP_GOTO_ON_ERROR(led_strip_spi_wait_trans_done(spi_strip), err, TAG, "wait for done failed");
    return ret;
err:
    atomic_store(&spi_strip->trans_state, LED_STRIP_TRANS_IDLE);
    return ret;
}

static esp_err_t led_strip_spi_clear(led_strip_t *strip)
{
    esp_err_t ret = ESP_OK;
    led_strip_spi_obj *spi_strip = __containerof(strip, led_strip_spi_obj, base);
    ESP_RETURN_ON_FALSE(led_strip_trans_state_try_set(&spi_strip->trans_state, LED_STRIP_TRANS_IDLE, LED_STRIP_TRANS_LOCKED),
                        ESP_ERR_INVALID_STATE, TAG, "SPI transaction is busy");
    //Write zero to turn off all leds
    memset(spi_strip->pixel_buf, 0, spi_strip->strip_len * spi_strip->bytes_per_pixel * SPI_BYTES_PER_COLOR_BYTE);
    uint8_t *buf = spi_strip->pixel_buf;
    for (int index = 0; index < spi_strip->strip_len * spi_strip->bytes_per_pixel; index++) {
        __led_strip_spi_bit(0, buf);
        buf += SPI_BYTES_PER_COLOR_BYTE;
    }

    ESP_GOTO_ON_ERROR(led_strip_spi_trans(spi_strip), err, TAG, "transmit pixels by SPI failed");
    ESP_GOTO_ON_ERROR(led_strip_spi_wait_trans_done(spi_strip), err, TAG, "wait for done failed");
    return ret;
err:
    atomic_store(&spi_strip->trans_state, LED_STRIP_TRANS_IDLE);
    return ret;
}

static esp_err_t led_strip_spi_del(led_strip_t *strip)
{
    esp_err_t ret = ESP_OK;
    led_strip_spi_obj *spi_strip = __containerof(strip, led_strip_spi_obj, base);

    ESP_RETURN_ON_FALSE(led_strip_trans_state_try_set(&spi_strip->trans_state, LED_STRIP_TRANS_IDLE, LED_STRIP_TRANS_LOCKED),
                        ESP_ERR_INVALID_STATE, TAG, "SPI transaction is busy");
    ESP_GOTO_ON_ERROR(spi_bus_remove_device(spi_strip->spi_device), err, TAG, "delete spi device failed");
    ESP_GOTO_ON_ERROR(spi_bus_free(spi_strip->spi_host), err, TAG, "free spi bus failed");

    free(spi_strip);
    return ret;
err:
    atomic_store(&spi_strip->trans_state, LED_STRIP_TRANS_IDLE);
    return ret;
}

esp_err_t led_strip_new_spi_device(const led_strip_config_t *led_config, const led_strip_spi_config_t *spi_config, led_strip_handle_t *ret_strip)
{
    led_strip_spi_obj *spi_strip = NULL;
    esp_err_t ret = ESP_OK;
    ESP_GOTO_ON_FALSE(led_config && spi_config && ret_strip, ESP_ERR_INVALID_ARG, err, TAG, "invalid argument");
    led_color_component_format_t component_fmt = led_config->color_component_format;
    uint32_t clock_speed_hz = LED_STRIP_SPI_DEFAULT_RESOLUTION;
    // If R/G/B order is not specified, set default GRB order as fallback
    if (component_fmt.format_id == 0) {
        component_fmt = LED_STRIP_COLOR_COMPONENT_FMT_GRB;
    }
    if (led_config->led_model == LED_MODEL_WS2816) {
        component_fmt.format.bytes_per_color = 2;
        clock_speed_hz = LED_STRIP_SPI_WS2816_RESOLUTION;
    }
    if (component_fmt.format.bytes_per_color == 0) {
        component_fmt.format.bytes_per_color = 1;
    }
    uint8_t mask = 0;
    if (component_fmt.format.num_components == 3) {
        mask = BIT(component_fmt.format.r_pos) | BIT(component_fmt.format.g_pos) | BIT(component_fmt.format.b_pos);
        // Check for invalid values
        ESP_RETURN_ON_FALSE(mask == 0x07, ESP_ERR_INVALID_ARG, TAG, "invalid order argument");
    } else if (component_fmt.format.num_components == 4) {
        mask = BIT(component_fmt.format.r_pos) | BIT(component_fmt.format.g_pos) | BIT(component_fmt.format.b_pos) | BIT(component_fmt.format.w_pos);
        // Check for invalid values
        ESP_RETURN_ON_FALSE(mask == 0x0F, ESP_ERR_INVALID_ARG, TAG, "invalid order argument");
    } else {
        ESP_RETURN_ON_FALSE(false, ESP_ERR_INVALID_ARG, TAG, "invalid number of color components: %d", component_fmt.format.num_components);
    }
    uint8_t bytes_per_pixel = component_fmt.format.num_components;
    if (component_fmt.format.bytes_per_color > 1) {
        bytes_per_pixel *= component_fmt.format.bytes_per_color;
    }
    uint32_t mem_caps = MALLOC_CAP_DEFAULT;
    if (spi_config->flags.with_dma) {
        // DMA buffer must be placed in internal SRAM
        mem_caps |= MALLOC_CAP_INTERNAL | MALLOC_CAP_DMA;
    }
    spi_strip = heap_caps_calloc(1, sizeof(led_strip_spi_obj) + led_config->max_leds * bytes_per_pixel * SPI_BYTES_PER_COLOR_BYTE, mem_caps);

    ESP_GOTO_ON_FALSE(spi_strip, ESP_ERR_NO_MEM, err, TAG, "no mem for spi strip");

    atomic_init(&spi_strip->trans_state, LED_STRIP_TRANS_IDLE);
    spi_strip->spi_host = spi_config->spi_bus;
    // for backward compatibility, if the user does not set the clk_src, use the default value
    spi_clock_source_t clk_src = SPI_CLK_SRC_DEFAULT;
    if (spi_config->clk_src) {
        clk_src = spi_config->clk_src;
    }

    spi_bus_config_t spi_bus_cfg = {
        .mosi_io_num = led_config->strip_gpio_num,
        //Only use MOSI to generate the signal, set -1 when other pins are not used.
        .miso_io_num = -1,
        .sclk_io_num = -1,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = led_config->max_leds * bytes_per_pixel * SPI_BYTES_PER_COLOR_BYTE,
    };
#ifdef SPICOMMON_BUSFLAG_DATA_OUT_INV
    if (led_config->flags.invert_out == true) {
        spi_bus_cfg.flags |= SPICOMMON_BUSFLAG_DATA_OUT_INV;
    }
#endif
    ESP_GOTO_ON_ERROR(spi_bus_initialize(spi_strip->spi_host, &spi_bus_cfg, spi_config->flags.with_dma ? SPI_DMA_CH_AUTO : SPI_DMA_DISABLED), err, TAG, "create SPI bus failed");

#ifndef SPICOMMON_BUSFLAG_DATA_OUT_INV
    if (led_config->flags.invert_out == true) {
        esp_rom_gpio_connect_out_signal(led_config->strip_gpio_num, spi_periph_signal[spi_strip->spi_host].spid_out, true, false);
    }
#endif
    spi_device_interface_config_t spi_dev_cfg = {
        .clock_source = clk_src,
        .command_bits = 0,
        .address_bits = 0,
        .dummy_bits = 0,
        .clock_speed_hz = clock_speed_hz,
        .mode = 0,
        //set -1 when CS is not used
        .spics_io_num = -1,
        .queue_size = LED_STRIP_SPI_DEFAULT_TRANS_QUEUE_SIZE,
    };

    ESP_GOTO_ON_ERROR(spi_bus_add_device(spi_strip->spi_host, &spi_dev_cfg, &spi_strip->spi_device), err, TAG, "Failed to add spi device");
    //ensure the reset time is enough
    esp_rom_delay_us(10);
    int clock_resolution_khz = 0;
    spi_device_get_actual_freq(spi_strip->spi_device, &clock_resolution_khz);
    // TODO: ideally we should decide the SPI_BYTES_PER_COLOR_BYTE by the real clock resolution
    // But now, let's fixed the resolution
    ESP_GOTO_ON_FALSE((clock_resolution_khz < clock_speed_hz / 1000 + 300) && (clock_resolution_khz > clock_speed_hz / 1000 - 300), ESP_ERR_NOT_SUPPORTED, err,
                      TAG, "unsupported clock resolution:%dKHz", clock_resolution_khz);

    if (led_config->led_model != LED_MODEL_WS2812 && led_config->led_model != LED_MODEL_WS2816) {
        ESP_LOGW(TAG, "Only support WS2812 and WS2816. The timing requirements for other models may not be met");
    }

    spi_strip->component_fmt = component_fmt;
    spi_strip->bytes_per_pixel = bytes_per_pixel;
    spi_strip->strip_len = led_config->max_leds;
    spi_strip->base.set_pixel = led_strip_spi_set_pixel;
    spi_strip->base.set_pixel_rgbw = led_strip_spi_set_pixel_rgbw;
    spi_strip->base.refresh = led_strip_spi_refresh;
    spi_strip->base.refresh_async = led_strip_spi_refresh_async;
    spi_strip->base.refresh_async_done = led_strip_spi_refresh_async_done;
    spi_strip->base.clear = led_strip_spi_clear;
    spi_strip->base.del = led_strip_spi_del;

    *ret_strip = &spi_strip->base;
    return ret;
err:
    if (spi_strip) {
        if (spi_strip->spi_device) {
            spi_bus_remove_device(spi_strip->spi_device);
        }
        if (spi_strip->spi_host) {
            spi_bus_free(spi_strip->spi_host);
        }
        free(spi_strip);
    }
    return ret;
}
