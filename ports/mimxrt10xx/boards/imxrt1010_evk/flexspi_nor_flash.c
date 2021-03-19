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

#include "board_api.h" // for logging

////////////////////////////////////////////////////////////////////////////////
// Definitions
////////////////////////////////////////////////////////////////////////////////

//! @name Alignment macros
//@{
#ifndef ALIGN_DOWN
#define ALIGN_DOWN(x, a) ((x) & -(a))
#endif
#ifndef ALIGN_UP
#define ALIGN_UP(x, a) (-(-(x) & -(a)))
#endif
//@}


////////////////////////////////////////////////////////////////////////////////
// Variables
////////////////////////////////////////////////////////////////////////////////
//extern const flexspi_nor_config_t qspiflash_config;

////////////////////////////////////////////////////////////////////////////////
// Local prototypes
////////////////////////////////////////////////////////////////////////////////
//uint32_t flexspi_nor_read_status(void);

////////////////////////////////////////////////////////////////////////////////
// Code
////////////////////////////////////////////////////////////////////////////////
/*
uint32_t flexspi_nor_read_status() {
    status_t status = kStatus_Fail;
    flexspi_xfer_t flashXfer;
    flexspi_mem_config_t *memCfg = (flexspi_mem_config_t *)&qspiflash_config;
    bool isParallelMode = flexspi_is_parallel_mode(memCfg);
    uint32_t readValue = 0;

    // Write enable 
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
*/
//!@brief Initialize Serial NOR devices via FlexSPI
status_t flexspi_nor_flash_init(uint32_t instance, flexspi_nor_config_t *config) {
    flexspi_mem_config_t *memCfg = (flexspi_mem_config_t *)config;
    status_t status = kStatus_Fail;
    status = flexspi_init(instance, memCfg);
    if (status != kStatus_Success) {
        TUF2_LOG1("FlexSPI initialization failed: 0x%08X\r\n", (uint)status);
    }

    // Configure Lookup table
    flexspi_update_lut(instance, 0, memCfg->lookupTable, 16);

    return status;
}

// See flexspi_nor_flash.h for more details.
status_t flexspi_nor_flash_erase_sector(uint32_t instance, flexspi_nor_config_t *config, uint32_t address)
{
    status_t status;
    flexspi_xfer_t flashXfer;
    bool isParallelMode;
    flexspi_mem_config_t *memCfg = (flexspi_mem_config_t *)config;
    isParallelMode = flexspi_is_parallel_mode(memCfg);

    do {
        status = flexspi_device_write_enable(instance, memCfg, isParallelMode, address);
        if (status != kStatus_Success) {
            break;
        }

        flashXfer.baseAddress = address;
        flashXfer.operation = kFlexSpiOperation_Command;
        flashXfer.seqNum = 1;
        flashXfer.seqId = NOR_CMD_LUT_SEQ_IDX_ERASESECTOR;
        flashXfer.isParallelModeEnable = isParallelMode;

        status = flexspi_command_xfer(instance, &flashXfer);
        if (status != kStatus_Success) {
            break;
        }

        // Wait until the sector erase operation completes on Serial NOR Flash side.
        status = flexspi_device_wait_busy(instance, memCfg, isParallelMode, address);
        if (status != kStatus_Success) {
            break;
        }

    } while (0);

    flexspi_clear_cache(instance);

    return status;
}

// See flexspi_nor_flash.h for more details.
status_t flexspi_nor_flash_erase(uint32_t instance, flexspi_nor_config_t *config, uint32_t start, uint32_t length) {
    uint32_t aligned_start;
    uint32_t aligned_end;

    status_t status = kStatus_InvalidArgument;

    do
    {
        if (config == NULL)
        {
            break;
        }

        aligned_start = ALIGN_DOWN(start, config->sectorSize);
        aligned_end = ALIGN_UP(start + length, config->sectorSize);

        while (aligned_start < aligned_end) {
            status = flexspi_nor_flash_erase_sector(instance, config, aligned_start);
            if (status != kStatus_Success) {
                return status;
            }
            aligned_start += config->sectorSize;
        }
    } while (0);

    return status;
}

/*
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
*/


// See flexspi_nor_flash.h for more details
status_t flexspi_nor_flash_page_program(uint32_t instance,
                                        flexspi_nor_config_t *config,
                                        uint32_t dstAddr,
                                        const uint32_t *src) {
    status_t status;
    flexspi_xfer_t flashXfer;
    flexspi_mem_config_t *memCfg = (flexspi_mem_config_t *)config;
    bool isParallelMode = flexspi_is_parallel_mode(memCfg);

    do {
        // Send write enable before executing page program command
        status = flexspi_device_write_enable(instance, memCfg, isParallelMode, dstAddr);
        if (status != kStatus_Success)
        {
            break;
        }

        // Prepare page program command
        flashXfer.operation = kFlexSpiOperation_Write;
        flashXfer.seqNum = 1;
        flashXfer.seqId = NOR_CMD_LUT_SEQ_IDX_PAGEPROGRAM;
        flashXfer.baseAddress = dstAddr;
        flashXfer.isParallelModeEnable = isParallelMode;
        flashXfer.txBuffer = (uint32_t *)src;
        flashXfer.txSize = config->pageSize;

        status = flexspi_command_xfer(instance, &flashXfer);
        if (status != kStatus_Success) {
            break;
        }

        // Wait until the program operation completes on Serial NOR Flash side.
        status = flexspi_device_wait_busy(instance, memCfg, isParallelMode, dstAddr);
        if (status != kStatus_Success) {
            break;
        }

    } while (0);

    flexspi_clear_cache(instance);

    return status;
}

/*
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
*/
