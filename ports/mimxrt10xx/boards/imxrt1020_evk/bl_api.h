/*
 * Copyright 2017-2020 NXP
 * All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#ifndef __BL_API_H__
#define __BL_API_H__

#include <string.h>
#include "bl_flexspi.h"
#include "flexspi_nor_flash.h"
#include "fsl_device_registers.h"

/*******************************************************************************
 * Definitions
 ******************************************************************************/
typedef struct
{
    uint32_t version;
    status_t (*init)(uint32_t instance, flexspi_nor_config_t *config);
    status_t (*program)(uint32_t instance, flexspi_nor_config_t *config, uint32_t dst_addr, const uint32_t *src);
    uint32_t reserved0;
    status_t (*erase)(uint32_t instance, flexspi_nor_config_t *config, uint32_t start, uint32_t lengthInBytes);
    uint32_t reserved1;
    void (*clear_cache)(uint32_t instance);
    status_t (*xfer)(uint32_t instance, flexspi_xfer_t *xfer);
    uint32_t reserved2;
    uint32_t reserved3;
} flexspi_nor_driver_interface_t;

enum
{
    kFlexSpiNorDriver_Version_1_5 = MAKE_VERSION(1, 4, 0),
};

typedef struct
{
    void (*runBootloader)(void *arg); //!< Function to start the bootloader executing
    const uint32_t version;           //!< Bootloader version number
    const char *copyright;            //!< Bootloader Copyright
    const uint32_t reserved0;
    const flexspi_nor_driver_interface_t *flexSpiNorDriver; //!< FlexSPI NOR Flash API
} bootloader_api_entry_t;

#endif //__BL_API_H__
