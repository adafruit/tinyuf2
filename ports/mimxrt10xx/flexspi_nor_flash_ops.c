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


////////////////////////////////////////////////////////////////////////////////
// Variables
////////////////////////////////////////////////////////////////////////////////
extern const flexspi_nor_config_t qspiflash_config;

////////////////////////////////////////////////////////////////////////////////
// Local prototypes
////////////////////////////////////////////////////////////////////////////////


////////////////////////////////////////////////////////////////////////////////
// Code
////////////////////////////////////////////////////////////////////////////////

void     flexspi_nor_flash_init(FLEXSPI_Type *base) {
    flexspi_mem_config_t *memCfg = (flexspi_mem_config_t *)&qspiflash_config;
    uint32_t instance = (uint32_t)base;
    status_t status = kStatus_InvalidArgument;
    status = flexspi_init(instance, memCfg);
    if (status != kStatus_Success) {
        TU_LOG1("FlexSPI initialization failed\r\n");
    }

    // Configure Lookup table for Read
//    flexspi_update_lut(instance, 0, config->memConfig.lookupTable, 1);

}

status_t flexspi_nor_flash_erase_sector(FLEXSPI_Type *base, uint32_t address) {
    status_t status;
    flexspi_xfer_t flashXfer;
    flexspi_mem_config_t *memCfg = (flexspi_mem_config_t *)&qspiflash_config;
    uint32_t instance = (uint32_t)base;
    bool isParallelMode = flexspi_is_parallel_mode(memCfg);

    do
    {
        status = flexspi_device_write_enable(instance, memCfg, isParallelMode, address);
        if (status != kStatus_Success)
        {
            TU_LOG1("FlexSPI write enable failed\r\n");
            break;
        }

        flashXfer.baseAddress = address;
        flashXfer.operation = kFlexSpiOperation_Command;
        flashXfer.seqNum = 1;
        flashXfer.seqId = NOR_CMD_LUT_SEQ_IDX_ERASESECTOR;
        flashXfer.isParallelModeEnable = isParallelMode;

        status = flexspi_command_xfer(instance, &flashXfer);
        if (status != kStatus_Success)
        {
            TU_LOG1("FlexSPI erase transfer failed\r\n");
            break;
        }

        // Wait until the sector erase operation completes on Serial NOR Flash side.
        status = flexspi_device_wait_busy(instance, memCfg, isParallelMode, address);
        if (status != kStatus_Success)
        {
            TU_LOG1("FlexSPI nor wait failed\r\n");
            break;
        }

    } while (0);

    flexspi_clear_cache(instance);

    return status;

}

status_t flexspi_nor_flash_page_program(FLEXSPI_Type *base, uint32_t dstAddr, uint32_t *src, uint32_t size) {
    status_t status;
    flexspi_xfer_t flashXfer;
    flexspi_mem_config_t *memCfg = (flexspi_mem_config_t *)&qspiflash_config;
    uint32_t instance = (uint32_t)base;
    bool isParallelMode = flexspi_is_parallel_mode(memCfg);

    do
    {
        // Send write enable before executing page program command
        status = flexspi_device_write_enable(instance, memCfg, isParallelMode, dstAddr);
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

        status = flexspi_command_xfer(instance, &flashXfer);
        if (status != kStatus_Success)
        {
            TU_LOG1("FlexSPI program page transfer failed\r\n");
            break;
        }

        // Wait until the program operation completes on Serial NOR Flash side.
        status = flexspi_device_wait_busy(instance, memCfg, isParallelMode, dstAddr);
        if (status != kStatus_Success)
        {
            break;
        }

    } while (0);

    flexspi_clear_cache(instance);

    return status;

}

