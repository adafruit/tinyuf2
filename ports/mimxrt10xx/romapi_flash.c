/*
 * Copyright 2016-2020 NXP
 * All rights reserved.
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Copyright (c) 2021 Ha Thach for Adafruit Industries
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

#include "romapi_flash.h"

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM DECLARATION
//--------------------------------------------------------------------+

#if defined(FSL_FEATURE_BOOT_ROM_HAS_ROMAPI) && FSL_FEATURE_BOOT_ROM_HAS_ROMAPI

// Some variants with ROM API but does not support erase_all API
#if !( defined(FSL_ROM_FLEXSPINOR_API_HAS_FEATURE_ERASE_ALL) && FSL_ROM_FLEXSPINOR_API_HAS_FEATURE_ERASE_ALL )

//static status_t rom_write_enable(uint32_t instance)
//{
//  ROM_FLEXSPI_NorFlash_CommandXfer(instance)
//}

status_t ROM_FLEXSPI_NorFlash_EraseAll(uint32_t instance, flexspi_nor_config_t *config)
{
//  status_t status;
//
//  status = rom_write_enable(instance);
//  if (status != kStatus_Success) return status;
//
//  return status;

  // TODO implement later
  return kStatus_Fail;
}
#endif


#else

// Some variant such as RT1011 does not have fsl_romapi for flash nor at all,
// therefore we need to implement it here

#ifndef ALIGN_DOWN
#define ALIGN_DOWN(x, a) ((x) & -(a))
#endif

#ifndef ALIGN_UP
#define ALIGN_UP(x, a) (-(-(x) & -(a)))
#endif

status_t ROM_FLEXSPI_NorFlash_Init (uint32_t instance, flexspi_nor_config_t *config)
{
  flexspi_mem_config_t *memCfg = (flexspi_mem_config_t*) config;
  status_t status = flexspi_init(instance, memCfg);

  if ( status != kStatus_Success )
  {
    //TUF2_LOG1("FlexSPI initialization failed: 0x%08X\r\n", (uint) status);
    return status;
  }

  // Configure Lookup table
  flexspi_update_lut(instance, 0, memCfg->lookupTable, 16);

  return status;
}

// See flexspi_nor_flash.h for more details.
status_t ROM_FLEXSPI_NorFlash_EraseSector (uint32_t instance, flexspi_nor_config_t *config, uint32_t address)
{
  status_t status;
  flexspi_xfer_t flashXfer;
  bool isParallelMode;
  flexspi_mem_config_t *memCfg = (flexspi_mem_config_t*) config;
  isParallelMode = flexspi_is_parallel_mode(memCfg);

  do
  {
    status = flexspi_device_write_enable(instance, memCfg, isParallelMode, address);
    if ( status != kStatus_Success )
    {
      break;
    }

    flashXfer.baseAddress = address;
    flashXfer.operation = kFlexSpiOperation_Command;
    flashXfer.seqNum = 1;
    flashXfer.seqId = NOR_CMD_LUT_SEQ_IDX_ERASESECTOR;
    flashXfer.isParallelModeEnable = isParallelMode;

    status = flexspi_command_xfer(instance, &flashXfer);
    if ( status != kStatus_Success )
    {
      break;
    }

    // Wait until the sector erase operation completes on Serial NOR Flash side.
    status = flexspi_device_wait_busy(instance, memCfg, isParallelMode, address);
    if ( status != kStatus_Success )
    {
      break;
    }

  } while ( 0 );

  flexspi_clear_cache(instance);

  return status;
}

// See flexspi_nor_flash.h for more details.
status_t ROM_FLEXSPI_NorFlash_Erase (uint32_t instance, flexspi_nor_config_t *config, uint32_t start, uint32_t length)
{
  uint32_t aligned_start;
  uint32_t aligned_end;

  status_t status = kStatus_InvalidArgument;

  do
  {
    if ( config == NULL )
    {
      break;
    }

    aligned_start = ALIGN_DOWN(start, config->sectorSize);
    aligned_end = ALIGN_UP(start + length, config->sectorSize);

    while ( aligned_start < aligned_end )
    {
      status = ROM_FLEXSPI_NorFlash_EraseSector(instance, config, aligned_start);
      if ( status != kStatus_Success )
      {
        return status;
      }
      aligned_start += config->sectorSize;
    }
  } while ( 0 );

  return status;
}

// See flexspi_nor_flash.h for more details
status_t ROM_FLEXSPI_NorFlash_ProgramPage (uint32_t instance, flexspi_nor_config_t *config, uint32_t dstAddr,
                                           const uint32_t *src)
{
  status_t status;
  flexspi_xfer_t flashXfer;
  flexspi_mem_config_t *memCfg = (flexspi_mem_config_t*) config;
  bool isParallelMode = flexspi_is_parallel_mode(memCfg);

  do
  {
    // Send write enable before executing page program command
    status = flexspi_device_write_enable(instance, memCfg, isParallelMode, dstAddr);
    if ( status != kStatus_Success )
    {
      break;
    }

    // Prepare page program command
    flashXfer.operation = kFlexSpiOperation_Write;
    flashXfer.seqNum = 1;
    flashXfer.seqId = NOR_CMD_LUT_SEQ_IDX_PAGEPROGRAM;
    flashXfer.baseAddress = dstAddr;
    flashXfer.isParallelModeEnable = isParallelMode;
    flashXfer.txBuffer = (uint32_t*) src;
    flashXfer.txSize = config->pageSize;

    status = flexspi_command_xfer(instance, &flashXfer);
    if ( status != kStatus_Success )
    {
      break;
    }

    // Wait until the program operation completes on Serial NOR Flash side.
    status = flexspi_device_wait_busy(instance, memCfg, isParallelMode, dstAddr);
    if ( status != kStatus_Success )
    {
      break;
    }

  } while ( 0 );

  flexspi_clear_cache(instance);

  return status;
}

status_t ROM_FLEXSPI_NorFlash_EraseAll (uint32_t instance, flexspi_nor_config_t *config)
{
  status_t status;
  flexspi_xfer_t flashXfer;
  bool isParallelMode;
  flexspi_mem_config_t *memCfg = (flexspi_mem_config_t*) config;
  isParallelMode = flexspi_is_parallel_mode(memCfg);

  do
  {
    status = flexspi_device_write_enable(instance, memCfg, isParallelMode, 0);
    if ( status != kStatus_Success )
    {
      break;
    }

    flashXfer.baseAddress = 0;
    flashXfer.operation = kFlexSpiOperation_Command;
    flashXfer.seqNum = 1;
    flashXfer.seqId = NOR_CMD_LUT_SEQ_IDX_CHIPERASE;
    flashXfer.isParallelModeEnable = isParallelMode;

    status = flexspi_command_xfer(instance, &flashXfer);
    if ( status != kStatus_Success )
    {
      break;
    }

    // Wait until the sector erase operation completes on Serial NOR Flash side.
    status = flexspi_device_wait_busy(instance, memCfg, isParallelMode, 0);
    if ( status != kStatus_Success )
    {
      break;
    }

  } while ( 0 );

  flexspi_clear_cache(instance);

  return status;
}

#endif
