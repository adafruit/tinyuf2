/*
 * SPDX-FileCopyrightText: 2026 Adafruit Industries
 * SPDX-License-Identifier: MIT
 */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// Early boot only, before any other RMT user. Accepts one scaled GRB pixel.
// Leaves the GPIO driven LOW, including after a transmission timeout.
bool bootloader_neopixel_write(uint32_t pin, const uint8_t *grb, size_t count);
