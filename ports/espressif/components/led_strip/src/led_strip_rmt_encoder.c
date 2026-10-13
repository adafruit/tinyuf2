/*
 * SPDX-FileCopyrightText: 2022-2025 Espressif Systems (Shanghai) CO LTD
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include "sdkconfig.h"
#include "esp_idf_version.h"
#include "esp_check.h"
#include "esp_attr.h"
#include "led_strip_rmt_encoder.h"

static const char *TAG = "led_rmt_encoder";

/** RMT symbol duration is a 15-bit field. */
#define LED_STRIP_RMT_DURATION_MAX 32767

static uint32_t led_strip_time_to_ticks(uint32_t time, uint32_t resolution_hz, uint64_t divisor)
{
    // Round up to avoid shortening timings that have a datasheet minimum.
    uint64_t duration = (uint64_t)time * resolution_hz;
    return (uint32_t)(duration / divisor + (duration % divisor != 0));
}

static bool led_strip_rmt_duration_in_range(uint32_t ticks)
{
    return ticks >= 1 && ticks <= LED_STRIP_RMT_DURATION_MAX;
}

#if ESP_IDF_VERSION < ESP_IDF_VERSION_VAL(5, 5, 0)
#if CONFIG_RMT_ISR_IRAM_SAFE
#define RMT_ENCODER_FUNC_ATTR IRAM_ATTR
#else
#define RMT_ENCODER_FUNC_ATTR
#endif // CONFIG_RMT_ISR_IRAM_SAFE
#endif // ESP_IDF_VERSION

typedef struct {
    rmt_encoder_t base;
    rmt_encoder_t *bytes_encoder;
    rmt_encoder_t *copy_encoder;
    int state;
    rmt_symbol_word_t reset_code;
} rmt_led_strip_encoder_t;

RMT_ENCODER_FUNC_ATTR
static size_t rmt_encode_led_strip(rmt_encoder_t *encoder, rmt_channel_handle_t channel, const void *primary_data, size_t data_size, rmt_encode_state_t *ret_state)
{
    rmt_led_strip_encoder_t *led_encoder = __containerof(encoder, rmt_led_strip_encoder_t, base);
    rmt_encoder_handle_t bytes_encoder = led_encoder->bytes_encoder;
    rmt_encoder_handle_t copy_encoder = led_encoder->copy_encoder;
    rmt_encode_state_t session_state = 0;
    rmt_encode_state_t state = 0;
    size_t encoded_symbols = 0;
    switch (led_encoder->state) {
    case 0: // send RGB data
        encoded_symbols += bytes_encoder->encode(bytes_encoder, channel, primary_data, data_size, &session_state);
        if (session_state & RMT_ENCODING_COMPLETE) {
            led_encoder->state = 1; // switch to next state when current encoding session finished
        }
        if (session_state & RMT_ENCODING_MEM_FULL) {
            state |= RMT_ENCODING_MEM_FULL;
            goto out; // yield if there's no free space for encoding artifacts
        }
    // fall-through
    case 1: // send reset code
        encoded_symbols += copy_encoder->encode(copy_encoder, channel, &led_encoder->reset_code,
                                                sizeof(led_encoder->reset_code), &session_state);
        if (session_state & RMT_ENCODING_COMPLETE) {
            led_encoder->state = 0; // back to the initial encoding session
            state |= RMT_ENCODING_COMPLETE;
        }
        if (session_state & RMT_ENCODING_MEM_FULL) {
            state |= RMT_ENCODING_MEM_FULL;
            goto out; // yield if there's no free space for encoding artifacts
        }
    }
out:
    *ret_state = state;
    return encoded_symbols;
}

static esp_err_t rmt_del_led_strip_encoder(rmt_encoder_t *encoder)
{
    rmt_led_strip_encoder_t *led_encoder = __containerof(encoder, rmt_led_strip_encoder_t, base);
    rmt_del_encoder(led_encoder->bytes_encoder);
    rmt_del_encoder(led_encoder->copy_encoder);
    free(led_encoder);
    return ESP_OK;
}

RMT_ENCODER_FUNC_ATTR
static esp_err_t rmt_led_strip_encoder_reset(rmt_encoder_t *encoder)
{
    rmt_led_strip_encoder_t *led_encoder = __containerof(encoder, rmt_led_strip_encoder_t, base);
    rmt_encoder_reset(led_encoder->bytes_encoder);
    rmt_encoder_reset(led_encoder->copy_encoder);
    led_encoder->state = 0;
    return ESP_OK;
}

esp_err_t rmt_new_led_strip_encoder(const led_strip_encoder_config_t *config, rmt_encoder_handle_t *ret_encoder)
{
    esp_err_t ret = ESP_OK;
    rmt_led_strip_encoder_t *led_encoder = NULL;
    ESP_GOTO_ON_FALSE(config && ret_encoder, ESP_ERR_INVALID_ARG, err, TAG, "invalid argument");
    led_encoder = calloc(1, sizeof(rmt_led_strip_encoder_t));
    ESP_GOTO_ON_FALSE(led_encoder, ESP_ERR_NO_MEM, err, TAG, "no mem for led strip encoder");
    led_encoder->base.encode = rmt_encode_led_strip;
    led_encoder->base.del = rmt_del_led_strip_encoder;
    led_encoder->base.reset = rmt_led_strip_encoder_reset;
    // Each duration is stored in a 15-bit RMT field, so reject values that become 0 or overflow.
    uint32_t t0h_ticks = led_strip_time_to_ticks(config->timings.t0h_ns, config->resolution, 1000000000);
    uint32_t t0l_ticks = led_strip_time_to_ticks(config->timings.t0l_ns, config->resolution, 1000000000);
    uint32_t t1h_ticks = led_strip_time_to_ticks(config->timings.t1h_ns, config->resolution, 1000000000);
    uint32_t t1l_ticks = led_strip_time_to_ticks(config->timings.t1l_ns, config->resolution, 1000000000);
    uint32_t reset_half_ticks = led_strip_time_to_ticks(config->timings.reset_us, config->resolution, 1000000 * 2);
    ESP_GOTO_ON_FALSE(led_strip_rmt_duration_in_range(t0h_ticks) && led_strip_rmt_duration_in_range(t0l_ticks) &&
                      led_strip_rmt_duration_in_range(t1h_ticks) && led_strip_rmt_duration_in_range(t1l_ticks) &&
                      led_strip_rmt_duration_in_range(reset_half_ticks),
                      ESP_ERR_INVALID_ARG, err, TAG, "timing is outside RMT duration range (1-%d ticks)", LED_STRIP_RMT_DURATION_MAX);
    rmt_bytes_encoder_config_t bytes_encoder_config = {
        .bit0 = {
            .level0 = 1,
            .duration0 = t0h_ticks,
            .level1 = 0,
            .duration1 = t0l_ticks,
        },
        .bit1 = {
            .level0 = 1,
            .duration0 = t1h_ticks,
            .level1 = 0,
            .duration1 = t1l_ticks,
        },
        .flags.msb_first = 1
    };
    uint32_t reset_ticks = reset_half_ticks;
    ESP_GOTO_ON_ERROR(rmt_new_bytes_encoder(&bytes_encoder_config, &led_encoder->bytes_encoder), err, TAG, "create bytes encoder failed");
    rmt_copy_encoder_config_t copy_encoder_config = {};
    ESP_GOTO_ON_ERROR(rmt_new_copy_encoder(&copy_encoder_config, &led_encoder->copy_encoder), err, TAG, "create copy encoder failed");

    led_encoder->reset_code = (rmt_symbol_word_t) {
        .level0 = 0,
        .duration0 = reset_ticks,
        .level1 = 0,
        .duration1 = reset_ticks,
    };
    *ret_encoder = &led_encoder->base;
    return ESP_OK;
err:
    if (led_encoder) {
        if (led_encoder->bytes_encoder) {
            rmt_del_encoder(led_encoder->bytes_encoder);
        }
        if (led_encoder->copy_encoder) {
            rmt_del_encoder(led_encoder->copy_encoder);
        }
        free(led_encoder);
    }
    return ret;
}
