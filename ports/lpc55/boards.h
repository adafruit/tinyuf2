/* 
 * The MIT License (MIT)
 *
 * Copyright (c) 2020 Ha Thach (tinyusb.org) for Adafruit Industries
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

#ifndef BOARDS_H_
#define BOARDS_H_

#ifdef __cplusplus
 extern "C" {
#endif

#include "board.h"

// Flash Start Address of Application
#define BOARD_FLASH_APP_START  0x10000 

#define USE_DFU_DOUBLE_TAP     0

//--------------------------------------------------------------------+
// IOCON Defines
//--------------------------------------------------------------------+

#define IOCON_PIO_ASW_DIS_EN     0x00u   /*!<@brief Analog switch is closed (enabled), only for A0 version */
#define IOCON_PIO_ASW_EN         0x0400u /*!<@brief Analog switch is closed (enabled) */
#define IOCON_PIO_DIGITAL_EN     0x0100u /*!<@brief Enables digital function */
#define IOCON_PIO_FUNC0          0x00u   /*!<@brief Selects pin function 0 */
#define IOCON_PIO_FUNC1          0x01u   /*!<@brief Selects pin function 1 */
#define IOCON_PIO_FUNC2          0x02u   /*!<@brief Selects pin function 7 */
#define IOCON_PIO_FUNC7          0x07u   /*!<@brief Selects pin function 7 */
#define IOCON_PIO_INV_DI         0x00u   /*!<@brief Input function is not inverted */
#define IOCON_PIO_MODE_INACT     0x00u   /*!<@brief No addition pin function */
#define IOCON_PIO_MODE_PULLUP    0x20u   /*!<@brief Selects pull-up function */
#define IOCON_PIO_OPENDRAIN_DI   0x00u   /*!<@brief Open drain is disabled */
#define IOCON_PIO_SLEW_STANDARD  0x00u   /*!<@brief Standard mode, output slew rate control is enabled */

#define IOCON_PIO_DIG_FUNC0_EN   (IOCON_PIO_DIGITAL_EN | IOCON_PIO_FUNC0) /*!<@brief Digital pin function 0 enabled */
#define IOCON_PIO_DIG_FUNC1_EN   (IOCON_PIO_DIGITAL_EN | IOCON_PIO_FUNC1) /*!<@brief Digital pin function 1 enabled */
#define IOCON_PIO_DIG_FUNC2_EN   (IOCON_PIO_DIGITAL_EN | IOCON_PIO_FUNC2) /*!<@brief Digital pin function 2 enabled */
#define IOCON_PIO_DIG_FUNC7_EN   (IOCON_PIO_DIGITAL_EN | IOCON_PIO_FUNC7) /*!<@brief Digital pin function 2 enabled */

#ifdef __cplusplus
 }
#endif

#endif /* BOARDS_H_ */
