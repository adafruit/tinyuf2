/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2021, Ha Thach (tinyusb.org)
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

// Some variant such as RT1011 does not have fsl_romapi at all,
// therefore we need to implement it here


#endif
