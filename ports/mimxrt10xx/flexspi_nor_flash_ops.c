/*
 * Copyright 2016-2020 NXP
 * All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 */

#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include "bl_flexspi.h"
#include "flexspi_nor_flash.h"
#include "tusb.h" // for loggin

////////////////////////////////////////////////////////////////////////////////
// Definitions
////////////////////////////////////////////////////////////////////////////////
#define FLEXSPI_INSTANCE  (uint32_t)0x0

////////////////////////////////////////////////////////////////////////////////
// Variables
////////////////////////////////////////////////////////////////////////////////
extern const flexspi_nor_config_t qspiflash_config;

////////////////////////////////////////////////////////////////////////////////
// Local prototypes
////////////////////////////////////////////////////////////////////////////////
uint32_t flexspi_nor_read_status(void);

////////////////////////////////////////////////////////////////////////////////
// Code
////////////////////////////////////////////////////////////////////////////////
uint32_t flexspi_nor_read_status() {
    status_t status = kStatus_Fail;
    flexspi_xfer_t flashXfer;
    flexspi_mem_config_t *memCfg = (flexspi_mem_config_t *)&qspiflash_config;
    bool isParallelMode = flexspi_is_parallel_mode(memCfg);
    uint32_t readValue = 0;

    /* Write enable */
    flashXfer.baseAddress = 0;
    flashXfer.operation = kFlexSpiOperation_Read;
    flashXfer.seqNum = 1;
    flashXfer.seqId = NOR_CMD_LUT_SEQ_IDX_READSTATUS;
    flashXfer.rxBuffer = &readValue;
    flashXfer.rxSize = 1;
    flashXfer.isParallelModeEnable = isParallelMode;

    status = flexspi_command_xfer(FLEXSPI_INSTANCE, &flashXfer);
    if (status != kStatus_Success) {
        TU_LOG1("FlexSPI read status transfer failed\r\n");
    }
    return readValue;
}


void     flexspi_nor_flash_init(FLEXSPI_Type *base) {

    flexspi_mem_config_t *memCfg = (flexspi_mem_config_t *)&qspiflash_config;
    status_t status = kStatus_Fail;
    status = flexspi_init(FLEXSPI_INSTANCE, memCfg);
    if (status != kStatus_Success) {
        TU_LOG1("FlexSPI initialization failed: 0x%08X\r\n", (uint)status);
    }

    // Configure Lookup table
    flexspi_update_lut(FLEXSPI_INSTANCE, 0, memCfg->lookupTable, 16);

    TU_LOG2("LUT Updated\r\n");
    TU_LOG2("LUT[0]:  0x%08X\r\n", (uint)FLEXSPI->LUT[0]);
    TU_LOG2("Wr En:   0x%08X\r\n", (uint)FLEXSPI->LUT[4 * NOR_CMD_LUT_SEQ_IDX_WRITEENABLE]);
    TU_LOG2("Erase:   0x%08X\r\n", (uint)FLEXSPI->LUT[4 * NOR_CMD_LUT_SEQ_IDX_ERASESECTOR]);
    TU_LOG2("Pgm Pg:  0x%08X\r\n", (uint)FLEXSPI->LUT[4 * NOR_CMD_LUT_SEQ_IDX_PAGEPROGRAM]);
    TU_LOG2("FCFB:    0x%08X\r\n", *(uint *)0x60000400);
    TU_LOG2("IVT 00:  0x%08X\r\n", *(uint *)0x60001000);
    TU_LOG2("IVT 04:  0x%08X\r\n", *(uint *)0x60001004);
    TU_LOG2("IVT 14:  0x%08X\r\n", *(uint *)0x60001014);
    TU_LOG2("Status:  0x%08X\r\n", (uint)flexspi_nor_read_status());

}

status_t flexspi_nor_flash_erase_sector(FLEXSPI_Type *base, uint32_t address) {
    status_t status = kStatus_Fail;
    flexspi_xfer_t flashXfer;
    flexspi_mem_config_t *memCfg = (flexspi_mem_config_t *)&qspiflash_config;
    bool isParallelMode = flexspi_is_parallel_mode(memCfg);

    do
    {
        status = flexspi_device_write_enable(FLEXSPI_INSTANCE, memCfg, isParallelMode, 0x0U);
        if (status != kStatus_Success)
        {
            TU_LOG1("FlexSPI write enable failed: 0x%08X\r\n", (uint)status);
            break;
        }

        flashXfer.baseAddress = address;
        flashXfer.operation = kFlexSpiOperation_Command;
        flashXfer.seqNum = 1;
        flashXfer.seqId = NOR_CMD_LUT_SEQ_IDX_ERASESECTOR;
        flashXfer.isParallelModeEnable = isParallelMode;

        status = flexspi_command_xfer(FLEXSPI_INSTANCE, &flashXfer);
        if (status != kStatus_Success)
        {
            TU_LOG1("FlexSPI erase transfer failed\r\n");
            break;
        }

        // Wait until the sector erase operation completes on Serial NOR Flash side.
        status = flexspi_device_wait_busy(FLEXSPI_INSTANCE, memCfg, isParallelMode, address);
        if (status != kStatus_Success)
        {
            TU_LOG1("FlexSPI nor wait failed\r\n");
            break;
        }

    } while (0);

    flexspi_clear_cache(FLEXSPI_INSTANCE);

    return status;

}

status_t flexspi_nor_flash_page_program(FLEXSPI_Type *base, uint32_t dstAddr, uint32_t *src, uint32_t size) {
    status_t status = kStatus_Fail;
    flexspi_xfer_t flashXfer;
    flexspi_mem_config_t *memCfg = (flexspi_mem_config_t *)&qspiflash_config;
    bool isParallelMode = flexspi_is_parallel_mode(memCfg);

    do
    {
        // Send write enable before executing page program command
        status = flexspi_device_write_enable(FLEXSPI_INSTANCE, memCfg, isParallelMode, 0x0U);
        if (status != kStatus_Success)
        {
            TU_LOG1("FlexSPI write enable failed\r\n");
            break;
        }

        // Prepare page program command
        flashXfer.operation = kFlexSpiOperation_Write;
        flashXfer.seqNum = 1;
        flashXfer.seqId = NOR_CMD_LUT_SEQ_IDX_PAGEPROGRAM;
        flashXfer.baseAddress = dstAddr;
        flashXfer.isParallelModeEnable = isParallelMode;
        flashXfer.txBuffer = (uint32_t *)src;
        flashXfer.txSize = size;

        status = flexspi_command_xfer(FLEXSPI_INSTANCE, &flashXfer);
        if (status != kStatus_Success)
        {
            TU_LOG1("FlexSPI program page transfer failed\r\n");
            break;
        }

        // Wait until the program operation completes on Serial NOR Flash side.
        status = flexspi_device_wait_busy(FLEXSPI_INSTANCE, memCfg, isParallelMode, dstAddr);
        if (status != kStatus_Success)
        {
            break;
        }

    } while (0);

    flexspi_clear_cache(FLEXSPI_INSTANCE);

    return status;

}

