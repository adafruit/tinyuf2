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

//--------------------------------------------------------------------+
// FlexSPI API
//--------------------------------------------------------------------+
bool flexspi_is_parallel_mode(flexspi_mem_config_t *config)
{
  bool (*const _flexspi_is_parallel_mode)(flexspi_mem_config_t *) = (bool (*)(flexspi_mem_config_t *))0x0020c687;
  return _flexspi_is_parallel_mode(config);
}

status_t flexspi_device_wait_busy(uint32_t instance, flexspi_mem_config_t *config, bool isParallelMode, uint32_t baseAddr)
{
  status_t (*const _flexspi_device_wait_busy)(uint32_t, flexspi_mem_config_t *, bool, uint32_t) =
      (status_t(*)(uint32_t, flexspi_mem_config_t *, bool, uint32_t))0x0020c025;
  return _flexspi_device_wait_busy(instance, config, isParallelMode, baseAddr);
}

status_t flexspi_command_xfer(uint32_t instance, flexspi_xfer_t *xfer)
{
  status_t (*const _flexspi_command_xfer)(uint32_t, flexspi_xfer_t *) =
      (status_t(*)(uint32_t, flexspi_xfer_t *))0x0020bb75;
  return _flexspi_command_xfer(instance, xfer);
}

status_t flexspi_update_lut(uint32_t instance, uint32_t seqIndex, const uint32_t *lutBase, uint32_t seqNumber)
{
  status_t (*const _flexspi_update_lut)(uint32_t, uint32_t, const uint32_t *, uint32_t) =
      (status_t(*)(uint32_t, uint32_t, const uint32_t *, uint32_t))0x0020c815;
  return _flexspi_update_lut(instance, seqIndex, lutBase, seqNumber);
}

void flexspi_clear_cache(uint32_t instance)
{
  void (*const _flexspi_clear_cache)(uint32_t) = (void (*)(uint32_t))0x0020ba3f;
  _flexspi_clear_cache(instance);
}

status_t flexspi_device_write_enable(uint32_t instance, flexspi_mem_config_t *config, bool isParallelMode, uint32_t baseAddr)
{
  status_t (*const _flexspi_device_write_enable)(uint32_t, flexspi_mem_config_t *, bool, uint32_t) =
      (status_t(*)(uint32_t, flexspi_mem_config_t *, bool, uint32_t))0x0020c1cd;
  return _flexspi_device_write_enable(instance, config, isParallelMode, baseAddr);
}

void flexspi_wait_idle(uint32_t instance)
{
  void (*const _flexspi_wait_idle)(uint32_t) = (void (*)(uint32_t))0x0020c87d;
  _flexspi_wait_idle(instance);
}

status_t flexspi_configure_dll(uint32_t instance, flexspi_mem_config_t *config)
{
  status_t (*const _flexspi_configure_dll)(uint32_t, flexspi_mem_config_t *) =
      (status_t(*)(uint32_t, flexspi_mem_config_t *))0x0020be25;
  return _flexspi_configure_dll(instance, config);
}

status_t flexspi_init(uint32_t instance, flexspi_mem_config_t *config)
{
  status_t (*const _flexspi_init)(uint32_t, flexspi_mem_config_t *) =
      (status_t(*)(uint32_t, flexspi_mem_config_t *))0x0020c339;
  return _flexspi_init(instance, config);
}

void flexspi_half_clock_control(uint32_t instance, uint32_t option)
{
  do
  {
    FLEXSPI_Type *(*const _flexspi_get_module_base)(uint32_t) = (FLEXSPI_Type * (*)(uint32_t))0x0020c2f1;
    FLEXSPI_Type *base = _flexspi_get_module_base(instance);

    if (base == NULL)
    {
      break;
    }

    void (*const _flexspi_wait_until_ip_idle)(FLEXSPI_Type *) = (void (*)(FLEXSPI_Type *))0x0020c893;
    _flexspi_wait_until_ip_idle(base);

    if (option)
    {
      base->MCR0 |= FLEXSPI_MCR0_HSEN_MASK;
    }
    else
    {
      base->MCR0 &= (uint32_t)~FLEXSPI_MCR0_HSEN_MASK;
    }

  } while (0);
}

//--------------------------------------------------------------------+
// Flash Nor API
//--------------------------------------------------------------------+

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

  if ( status != kStatus_Success ) return status;

  // Configure Lookup table
  flexspi_update_lut(instance, 0, memCfg->lookupTable, 16);

  return status;
}

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
