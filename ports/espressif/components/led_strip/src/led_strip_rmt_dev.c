/*
 * SPDX-FileCopyrightText: 2022-2025 Espressif Systems (Shanghai) CO LTD
 *
 * SPDX-License-Identifier: Apache-2.0
 */
#include <stdlib.h>
#include <string.h>
#include <sys/cdefs.h>
#include "esp_log.h"
#include "esp_check.h"
#include "driver/rmt_tx.h"
#include "led_strip.h"
#include "led_strip_interface.h"
#include "led_strip_rmt_encoder.h"
#include "led_strip_common.h"

#define LED_STRIP_RMT_DEFAULT_RESOLUTION 10000000 // 10MHz resolution
#define LED_STRIP_RMT_DEFAULT_TRANS_QUEUE_SIZE 4
// the memory size of each RMT channel, in words (4 bytes)
#if CONFIG_IDF_TARGET_ESP32 || CONFIG_IDF_TARGET_ESP32S2
#define LED_STRIP_RMT_DEFAULT_MEM_BLOCK_SYMBOLS 64
#else
#define LED_STRIP_RMT_DEFAULT_MEM_BLOCK_SYMBOLS 48
#endif

static const char *TAG = "led_strip_rmt";

typedef struct {
    led_strip_t base;
    rmt_channel_handle_t rmt_chan;
    rmt_encoder_handle_t strip_encoder;
    uint32_t strip_len;
    uint8_t bytes_per_pixel;
    led_color_component_format_t component_fmt;
    led_strip_trans_state_atomic_t trans_state;
    uint8_t pixel_buf[];
} led_strip_rmt_obj;

static esp_err_t led_strip_rmt_trans(led_strip_rmt_obj *rmt_strip)
{
    esp_err_t ret = ESP_OK;
    rmt_transmit_config_t tx_conf = {
        .loop_count = 0,
    };

    ESP_RETURN_ON_ERROR(rmt_enable(rmt_strip->rmt_chan), TAG, "enable RMT channel failed");
    ESP_GOTO_ON_ERROR(rmt_transmit(rmt_strip->rmt_chan, rmt_strip->strip_encoder, rmt_strip->pixel_buf,
                                   rmt_strip->strip_len * rmt_strip->bytes_per_pixel, &tx_conf), err, TAG, "transmit pixels by RMT failed");
    return ret;
err:
    rmt_disable(rmt_strip->rmt_chan);
    return ret;
}

static esp_err_t led_strip_rmt_wait_trans_done(led_strip_rmt_obj *rmt_strip)
{
    ESP_RETURN_ON_ERROR(rmt_tx_wait_all_done(rmt_strip->rmt_chan, -1), TAG, "wait for RMT done failed");
    ESP_RETURN_ON_ERROR(rmt_disable(rmt_strip->rmt_chan), TAG, "disable RMT channel failed");
    atomic_store(&rmt_strip->trans_state, LED_STRIP_TRANS_IDLE);
    return ESP_OK;
}

static esp_err_t led_strip_rmt_set_pixel(led_strip_t *strip, uint32_t index, uint32_t red, uint32_t green, uint32_t blue)
{
    led_strip_rmt_obj *rmt_strip = __containerof(strip, led_strip_rmt_obj, base);
    ESP_RETURN_ON_FALSE(index < rmt_strip->strip_len, ESP_ERR_INVALID_ARG, TAG, "index out of maximum number of LEDs");
    ESP_RETURN_ON_FALSE(led_strip_trans_state_try_set(&rmt_strip->trans_state, LED_STRIP_TRANS_IDLE, LED_STRIP_TRANS_LOCKED),
                        ESP_ERR_INVALID_STATE, TAG, "RMT transaction is busy");

    struct format_layout format = rmt_strip->component_fmt.format;
    uint32_t start = index * rmt_strip->bytes_per_pixel;
    uint8_t *pixel_buf = rmt_strip->pixel_buf;
    uint8_t pos_bytes = format.bytes_per_color;

    for (uint8_t i = 0; i < format.bytes_per_color; i++) {
        uint8_t color_shift = 8 * (format.bytes_per_color - 1 - i);
        pixel_buf[start + format.r_pos * pos_bytes + i] = (red >> color_shift) & 0xFF;
        pixel_buf[start + format.g_pos * pos_bytes + i] = (green >> color_shift) & 0xFF;
        pixel_buf[start + format.b_pos * pos_bytes + i] = (blue >> color_shift) & 0xFF;
        if (format.num_components > 3) {
            pixel_buf[start + format.w_pos * pos_bytes + i] = 0;
        }
    }
    atomic_store(&rmt_strip->trans_state, LED_STRIP_TRANS_IDLE);
    return ESP_OK;
}

static esp_err_t led_strip_rmt_set_pixel_rgbw(led_strip_t *strip, uint32_t index, uint32_t red, uint32_t green, uint32_t blue, uint32_t white)
{
    led_strip_rmt_obj *rmt_strip = __containerof(strip, led_strip_rmt_obj, base);
    struct format_layout format = rmt_strip->component_fmt.format;
    ESP_RETURN_ON_FALSE(index < rmt_strip->strip_len, ESP_ERR_INVALID_ARG, TAG, "index out of maximum number of LEDs");
    ESP_RETURN_ON_FALSE(format.num_components == 4, ESP_ERR_INVALID_ARG, TAG, "led doesn't have 4 components");
    ESP_RETURN_ON_FALSE(led_strip_trans_state_try_set(&rmt_strip->trans_state, LED_STRIP_TRANS_IDLE, LED_STRIP_TRANS_LOCKED),
                        ESP_ERR_INVALID_STATE, TAG, "RMT transaction is busy");

    uint32_t start = index * rmt_strip->bytes_per_pixel;
    uint8_t *pixel_buf = rmt_strip->pixel_buf;
    uint8_t pos_bytes = format.bytes_per_color;

    for (uint8_t i = 0; i < format.bytes_per_color; i++) {
        uint8_t color_shift = 8 * (format.bytes_per_color - 1 - i);
        pixel_buf[start + format.r_pos * pos_bytes + i] = (red >> color_shift) & 0xFF;
        pixel_buf[start + format.g_pos * pos_bytes + i] = (green >> color_shift) & 0xFF;
        pixel_buf[start + format.b_pos * pos_bytes + i] = (blue >> color_shift) & 0xFF;
        pixel_buf[start + format.w_pos * pos_bytes + i] = (white >> color_shift) & 0xFF;
    }
    atomic_store(&rmt_strip->trans_state, LED_STRIP_TRANS_IDLE);
    return ESP_OK;
}

static esp_err_t led_strip_rmt_refresh_async(led_strip_t *strip)
{
    esp_err_t ret = ESP_OK;
    led_strip_rmt_obj *rmt_strip = __containerof(strip, led_strip_rmt_obj, base);
    ESP_RETURN_ON_FALSE(led_strip_trans_state_try_set(&rmt_strip->trans_state, LED_STRIP_TRANS_IDLE, LED_STRIP_TRANS_INFLIGHT),
                        ESP_ERR_INVALID_STATE, TAG, "RMT transaction is busy");
    ESP_GOTO_ON_ERROR(led_strip_rmt_trans(rmt_strip), err, TAG, "start RMT transaction failed");
    return ret;
err:
    atomic_store(&rmt_strip->trans_state, LED_STRIP_TRANS_IDLE);
    return ret;
}

static esp_err_t led_strip_rmt_refresh_async_done(led_strip_t *strip)
{
    esp_err_t ret = ESP_OK;
    led_strip_rmt_obj *rmt_strip = __containerof(strip, led_strip_rmt_obj, base);
    ESP_RETURN_ON_FALSE(led_strip_trans_state_try_set(&rmt_strip->trans_state, LED_STRIP_TRANS_INFLIGHT, LED_STRIP_TRANS_LOCKED),
                        ESP_ERR_INVALID_STATE, TAG, "no async refresh in progress");
    ESP_GOTO_ON_ERROR(led_strip_rmt_wait_trans_done(rmt_strip), err, TAG, "wait for done failed");
    return ret;
err:
    atomic_store(&rmt_strip->trans_state, LED_STRIP_TRANS_INFLIGHT);
    return ret;
}

static esp_err_t led_strip_rmt_refresh(led_strip_t *strip)
{
    esp_err_t ret = ESP_OK;
    led_strip_rmt_obj *rmt_strip = __containerof(strip, led_strip_rmt_obj, base);
    ESP_RETURN_ON_FALSE(led_strip_trans_state_try_set(&rmt_strip->trans_state, LED_STRIP_TRANS_IDLE, LED_STRIP_TRANS_LOCKED),
                        ESP_ERR_INVALID_STATE, TAG, "RMT transaction is busy");
    ESP_GOTO_ON_ERROR(led_strip_rmt_trans(rmt_strip), err, TAG, "start RMT transaction failed");
    ESP_GOTO_ON_ERROR(led_strip_rmt_wait_trans_done(rmt_strip), err, TAG, "wait for done failed");
    return ret;
err:
    atomic_store(&rmt_strip->trans_state, LED_STRIP_TRANS_IDLE);
    return ret;
}

static esp_err_t led_strip_rmt_clear(led_strip_t *strip)
{
    esp_err_t ret = ESP_OK;
    led_strip_rmt_obj *rmt_strip = __containerof(strip, led_strip_rmt_obj, base);
    ESP_RETURN_ON_FALSE(led_strip_trans_state_try_set(&rmt_strip->trans_state, LED_STRIP_TRANS_IDLE, LED_STRIP_TRANS_LOCKED),
                        ESP_ERR_INVALID_STATE, TAG, "RMT transaction is busy");
    // Write zero to turn off all leds
    memset(rmt_strip->pixel_buf, 0, rmt_strip->strip_len * rmt_strip->bytes_per_pixel);
    ESP_GOTO_ON_ERROR(led_strip_rmt_trans(rmt_strip), err, TAG, "start RMT transaction failed");
    ESP_GOTO_ON_ERROR(led_strip_rmt_wait_trans_done(rmt_strip), err, TAG, "wait for done failed");
    return ret;
err:
    atomic_store(&rmt_strip->trans_state, LED_STRIP_TRANS_IDLE);
    return ret;
}

static esp_err_t led_strip_rmt_del(led_strip_t *strip)
{
    esp_err_t ret = ESP_OK;
    led_strip_rmt_obj *rmt_strip = __containerof(strip, led_strip_rmt_obj, base);
    ESP_RETURN_ON_FALSE(led_strip_trans_state_try_set(&rmt_strip->trans_state, LED_STRIP_TRANS_IDLE, LED_STRIP_TRANS_LOCKED),
                        ESP_ERR_INVALID_STATE, TAG, "RMT transaction is busy");
    ESP_GOTO_ON_ERROR(rmt_del_channel(rmt_strip->rmt_chan), err, TAG, "delete RMT channel failed");
    ESP_GOTO_ON_ERROR(rmt_del_encoder(rmt_strip->strip_encoder), err, TAG, "delete strip encoder failed");
    free(rmt_strip);
    return ret;
err:
    atomic_store(&rmt_strip->trans_state, LED_STRIP_TRANS_IDLE);
    return ret;
}

static esp_err_t led_strip_rmt_switch_gpio(led_strip_t *strip, gpio_num_t new_gpio_num, bool invert_output)
{
    esp_err_t ret = ESP_OK;
    led_strip_rmt_obj *rmt_strip = __containerof(strip, led_strip_rmt_obj, base);
    ESP_RETURN_ON_FALSE(led_strip_trans_state_try_set(&rmt_strip->trans_state, LED_STRIP_TRANS_IDLE, LED_STRIP_TRANS_LOCKED),
                        ESP_ERR_INVALID_STATE, TAG, "RMT transaction is busy");
    ret = rmt_tx_switch_gpio(rmt_strip->rmt_chan, new_gpio_num, invert_output);
    atomic_store(&rmt_strip->trans_state, LED_STRIP_TRANS_IDLE);
    return ret;
}

static esp_err_t led_strip_get_timings(led_model_t led_model, const led_strip_timings_t *custom_timings, led_strip_timings_t *timings)
{
    if (led_model == LED_MODEL_CUSTOM) {
        *timings = *custom_timings;
        return ESP_OK;
    }

    switch (led_model) {
    case LED_MODEL_WS2812:
        *timings = (led_strip_timings_t) {
            .t0h_ns = 300,
            .t1h_ns = 900,
            .t0l_ns = 900,
            .t1l_ns = 600,
            .reset_us = 280,
        };
        break;
    case LED_MODEL_SK6812:
        *timings = (led_strip_timings_t) {
            .t0h_ns = 300,
            .t1h_ns = 700,
            .t0l_ns = 900,
            .t1l_ns = 600,
            .reset_us = 280,
        };
        break;
    case LED_MODEL_WS2811:
        *timings = (led_strip_timings_t) {
            .t0h_ns = 500,
            .t1h_ns = 1200,
            .t0l_ns = 2000,
            .t1l_ns = 1300,
            .reset_us = 50,
        };
        break;
    case LED_MODEL_WS2816:
        *timings = (led_strip_timings_t) {
            .t0h_ns = 300,
            .t1h_ns = 750,
            .t0l_ns = 950,
            .t1l_ns = 500,
            .reset_us = 280,
        };
        break;
    default:
        return ESP_ERR_INVALID_ARG;
    }
    return ESP_OK;
}

esp_err_t led_strip_new_rmt_device(const led_strip_config_t *led_config, const led_strip_rmt_config_t *rmt_config, led_strip_handle_t *ret_strip)
{
    led_strip_rmt_obj *rmt_strip = NULL;
    esp_err_t ret = ESP_OK;
    ESP_GOTO_ON_FALSE(led_config && rmt_config && ret_strip, ESP_ERR_INVALID_ARG, err, TAG, "invalid argument");
    led_strip_timings_t timings;
    ESP_GOTO_ON_ERROR(led_strip_get_timings(led_config->led_model, &led_config->timings, &timings), err, TAG, "invalid LED model");
    led_color_component_format_t component_fmt = led_config->color_component_format;
    // If R/G/B order is not specified, set default GRB order as fallback
    if (component_fmt.format_id == 0) {
        component_fmt = LED_STRIP_COLOR_COMPONENT_FMT_GRB;
    }
    if (led_config->led_model == LED_MODEL_WS2816) {
        component_fmt.format.bytes_per_color = 2;
    }
    if (component_fmt.format.bytes_per_color == 0) {
        component_fmt.format.bytes_per_color = 1;
    }
    // check the validation of the color component format
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
    rmt_strip = calloc(1, sizeof(led_strip_rmt_obj) + led_config->max_leds * bytes_per_pixel);
    ESP_GOTO_ON_FALSE(rmt_strip, ESP_ERR_NO_MEM, err, TAG, "no mem for rmt strip");
    atomic_init(&rmt_strip->trans_state, LED_STRIP_TRANS_IDLE);
    uint32_t resolution = rmt_config->resolution_hz ? rmt_config->resolution_hz : LED_STRIP_RMT_DEFAULT_RESOLUTION;

    // for backward compatibility, if the user does not set the clk_src, use the default value
    rmt_clock_source_t clk_src = RMT_CLK_SRC_DEFAULT;
    if (rmt_config->clk_src) {
        clk_src = rmt_config->clk_src;
    }
    size_t mem_block_symbols = LED_STRIP_RMT_DEFAULT_MEM_BLOCK_SYMBOLS;
    // override the default value if the user sets it
    if (rmt_config->mem_block_symbols) {
        mem_block_symbols = rmt_config->mem_block_symbols;
    }
    rmt_tx_channel_config_t rmt_chan_config = {
        .clk_src = clk_src,
        .gpio_num = led_config->strip_gpio_num,
        .mem_block_symbols = mem_block_symbols,
        .resolution_hz = resolution,
        .trans_queue_depth = LED_STRIP_RMT_DEFAULT_TRANS_QUEUE_SIZE,
        .flags.with_dma = rmt_config->flags.with_dma,
        .flags.invert_out = led_config->flags.invert_out,
    };
    ESP_GOTO_ON_ERROR(rmt_new_tx_channel(&rmt_chan_config, &rmt_strip->rmt_chan), err, TAG, "create RMT TX channel failed");

    led_strip_encoder_config_t strip_encoder_conf = {
        .resolution = resolution,
        .timings = timings,
    };
    ESP_GOTO_ON_ERROR(rmt_new_led_strip_encoder(&strip_encoder_conf, &rmt_strip->strip_encoder), err, TAG, "create LED strip encoder failed");

    rmt_strip->component_fmt = component_fmt;
    rmt_strip->bytes_per_pixel = bytes_per_pixel;
    rmt_strip->strip_len = led_config->max_leds;
    rmt_strip->base.set_pixel = led_strip_rmt_set_pixel;
    rmt_strip->base.set_pixel_rgbw = led_strip_rmt_set_pixel_rgbw;
    rmt_strip->base.refresh = led_strip_rmt_refresh;
    rmt_strip->base.refresh_async = led_strip_rmt_refresh_async;
    rmt_strip->base.refresh_async_done = led_strip_rmt_refresh_async_done;
    rmt_strip->base.switch_gpio = led_strip_rmt_switch_gpio;
    rmt_strip->base.clear = led_strip_rmt_clear;
    rmt_strip->base.del = led_strip_rmt_del;

    *ret_strip = &rmt_strip->base;
    return ret;
err:
    if (rmt_strip) {
        if (rmt_strip->rmt_chan) {
            rmt_del_channel(rmt_strip->rmt_chan);
        }
        if (rmt_strip->strip_encoder) {
            rmt_del_encoder(rmt_strip->strip_encoder);
        }
        free(rmt_strip);
    }
    return ret;
}
