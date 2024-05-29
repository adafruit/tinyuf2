/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2021 Greg Steiert for NXP
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#ifndef KUIIC_RGB_H_
#define KUIIC_RGB_H_

#include <stdint.h>

//--------------------------------------------------------------------+
// Definitions
//--------------------------------------------------------------------+
#define KUIIC_RGB_DMA_CHANNEL    0U
#define KUIIC_RGB_DMA_SOURCE     56U
#define KUIIC_RGB_TPM_SC_GO      0x10C
#define KUIIC_RGB_TPM_SC_STOP    0x084
#define KUIIC_RGB_TPM            TPM2
#define KUIIC_RGB_BR_CH          0U
#define KUIIC_RGB_GB_CH          1U
#define KUIIC_RGB_BRIGHT_SHIFT   4
#define KUIIC_RGB_CLK_PORT       kCLOCK_PortA
#define KUIIC_RGB_BR_PORT        PORTA
#define KUIIC_RGB_BR_PIN         1
#define KUIIC_RGB_BR_MUX         kPORT_MuxAlt3
#define KUIIC_RGB_GB_PORT        PORTA
#define KUIIC_RGB_GB_PIN         2
#define KUIIC_RGB_GB_MUX         kPORT_MuxAlt3

//--------------------------------------------------------------------+
// Basic API
//--------------------------------------------------------------------+

/*! @brief KUIIC RGB initialization
 */
void kuiic_rgb_init(void);

/*! @brief KUIIC RGB write function
 *  @param byte array for RGB values to be written
 */
void kuiic_rgb_write(uint8_t const rgb[]);

/*! @brief KUIIC RGB tick handler
 *  @note This should be called in the systick handler to
 *        initiate the next pulses
 */
void kuiic_rgb_tick(void);

#endif
