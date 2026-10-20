/*
 * SPDX-FileCopyrightText: 2022-2026 Espressif Systems (Shanghai) CO LTD
 *
 * SPDX-License-Identifier: Apache-2.0
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"
#include "hal/gpio_types.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct led_strip_t led_strip_t; /*!< Type of LED strip */

/**
 * @brief LED strip interface definition
 */
struct led_strip_t {
    /**
     * @brief Set RGB for a specific pixel
     *
     * @param strip: LED strip
     * @param index: index of pixel to set
     * @param red: red part of color
     * @param green: green part of color
     * @param blue: blue part of color
     *
     * @return
     *      - ESP_OK: Set RGB for a specific pixel successfully
     *      - ESP_ERR_INVALID_ARG: Set RGB for a specific pixel failed because of invalid parameters
     *      - ESP_FAIL: Set RGB for a specific pixel failed because other error occurred
     */
    esp_err_t (*set_pixel)(led_strip_t *strip, uint32_t index, uint32_t red, uint32_t green, uint32_t blue);

    /**
     * @brief Set RGBW for a specific pixel. Similar to `set_pixel` but also set the white component
     *
     * @param strip: LED strip
     * @param index: index of pixel to set
     * @param red: red part of color
     * @param green: green part of color
     * @param blue: blue part of color
     * @param white: separate white component
     *
     * @return
     *      - ESP_OK: Set RGBW color for a specific pixel successfully
     *      - ESP_ERR_INVALID_ARG: Set RGBW color for a specific pixel failed because of an invalid argument
     *      - ESP_FAIL: Set RGBW color for a specific pixel failed because other error occurred
     */
    esp_err_t (*set_pixel_rgbw)(led_strip_t *strip, uint32_t index, uint32_t red, uint32_t green, uint32_t blue, uint32_t white);

    /**
     * @brief Refresh memory colors to LEDs
     *
     * @param strip: LED strip
     *
     * @return
     *      - ESP_OK: Refresh successfully
     *      - ESP_FAIL: Refresh failed because some other error occurred
     *
     * @note After updating the LED colors in the memory, a following invocation of this API is needed to flush colors to strip.
     */
    esp_err_t (*refresh)(led_strip_t *strip);

    /**
     * @brief Refresh memory colors to LEDs asynchronously
     *
     * @param strip: LED strip
     *
     * @return
     *      - ESP_OK: Refresh successfully
     *      - ESP_FAIL: Refresh failed because some other error occurred
     *
     * @note This function is non-blocking, but the driver does not have a double buffer yet, so the pixel buffer is
     *       shared with the in-flight transaction. You still have to call `led_strip_refresh_async_done()` before
     *       modifying the LED colors again.
     */
    esp_err_t (*refresh_async)(led_strip_t *strip);

    /**
     * @brief Wait for the async refresh to complete
     *
     * @param strip: LED strip
     *
     * @return
     *      - ESP_OK: Wait for the async refresh to complete successfully
     *      - ESP_ERR_INVALID_STATE: Wait failed because there is no in-flight async refresh
     */
    esp_err_t (*refresh_async_done)(led_strip_t *strip);

    /**
     * @brief Clear LED strip (turn off all LEDs)
     *
     * @param strip: LED strip
     *
     * @return
     *      - ESP_OK: Clear LEDs successfully
     *      - ESP_FAIL: Clear LEDs failed because some other error occurred
     */
    esp_err_t (*clear)(led_strip_t *strip);

    /**
     * @brief Switch GPIO of LED strip
     *
     * @param strip: LED strip
     * @param new_gpio_num: new GPIO number
     * @param invert_output: invert output
     *
     * @note Only support RMT backend now
     *
     * @return
     *      - ESP_OK: Switch GPIO successfully
     *      - ESP_FAIL: Switch GPIO failed because some other error occurred
     */
    esp_err_t (*switch_gpio)(led_strip_t *strip, gpio_num_t new_gpio_num, bool invert_output);

    /**
     * @brief Free LED strip resources
     *
     * @param strip: LED strip
     *
     * @return
     *      - ESP_OK: Free resources successfully
     *      - ESP_FAIL: Free resources failed because error occurred
     */
    esp_err_t (*del)(led_strip_t *strip);
};

#ifdef __cplusplus
}
#endif
