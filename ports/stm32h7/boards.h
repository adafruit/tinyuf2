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

#include "stm32h7xx.h"
#include "stm32h7xx_hal_conf.h"
#include "stm32h7xx_hal.h"

#include "board.h"

// depending on internal or external flash
// #define BOARD_FLASH_ADDR_ZERO   0x08000000

// Flash Start Address of Application
// #define BOARD_FLASH_APP_START   0x08010000
// #define BOARD_FLASH_APP_START   0x90000000

// Boot address list
// The memory last flashed by tinyuf2 will be used
// NOTE: The default ST SystemInit set VTOR to either of 0x08000000 or 0x24000000
// So you can copy your vector table after boot (compile with VECT_TAB_SRAM)
#define BOARD_QSPI_APP_ADDR   QSPI_BASE_ADDR
// First 64Kbytes is for tinyuf2
// The application must not use it after boot
#define BOARD_PFLASH_APP_ADDR (PFLASH_BASE_ADDR + PFLASH_OFFS)
// First 64Kbytes are for tinyuf2
// The application can use it after boot
#define BOARD_AXISRAM_APP_ADDR (AXISRAM_BASE_ADDR + AXISRAM_OFFS)

#define SPI_BASE_ADDR     0x60000000U
#define QSPI_BASE_ADDR    0x90000000U
#define PFLASH_BASE_ADDR  0x08000000U
#define AXISRAM_BASE_ADDR 0x24000000U

#define SPI_FLASH_SIZE    8*1024*1024 // 8Mbytes
#define QSPI_FLASH_SIZE   8*1024*1024 // 8Mbytes
#define PFLASH_SIZE       128*1024 // 128Kbytes
#define AXISRAM_SIZE      256*1024 // 512Kbytes

#define SPI_FLASH_OFFS  0U
#define QSPI_FLASH_OFFS 0U
#define PFLASH_OFFS     64*1024 // 64Kbyte offset
#define AXISRAM_OFFS    0U

#define IS_SPI_ADDR(x)      (((x) >= SPI_BASE_ADDR) && ((x) < (SPI_BASE_ADDR + SPI_FLASH_SIZE)))
#define IS_QSPI_ADDR(x)     (((x) >= QSPI_BASE_ADDR) && ((x) < (QSPI_BASE_ADDR + QSPI_FLASH_SIZE)))
#define IS_PFLASH_ADDR(x)   (((x) >= (PFLASH_BASE_ADDR + PFLASH_SIZE/2)) && ((x) < (PFLASH_BASE_ADDR + PFLASH_SIZE)))
#define IS_AXISRAM_ADDR(x)  (((x) >= (AXISRAM_BASE_ADDR + AXISRAM_OFFS)) && ((x) < (AXISRAM_BASE_ADDR + AXISRAM_SIZE)))

#define SET_BOOT_ADDR(x) board_save_app_start_address(x)

// Double Reset tap to enter DFU
#define TINYUF2_DBL_TAP_DFU  1

void board_flash_early_init(void);
uint32_t board_get_app_start_address(void);
void board_save_app_start_address(uint32_t addr);
void board_clear_temp_boot_addr(void);
void board_flash_deinit(void);

#ifdef __cplusplus
 }
#endif

#endif /* BOARDS_H_ */
