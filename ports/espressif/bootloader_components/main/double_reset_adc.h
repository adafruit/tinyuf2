/*
 * SPDX-FileCopyrightText: 2026 Adafruit Industries
 * SPDX-License-Identifier: MIT
 */
#pragma once

#include <stdbool.h>

// Call after bootloader_init(), before charging the marker capacitor.
bool double_reset_adc_detect(void);
void double_reset_adc_arm(void);
void double_reset_adc_clear(void);
