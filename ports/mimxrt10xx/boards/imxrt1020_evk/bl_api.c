/*
 * Copyright 2017-2019 NXP
 * All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include "bl_api.h"

/*******************************************************************************
 * Prototypes
 ******************************************************************************/

/*******************************************************************************
 * Variables
 ******************************************************************************/
#define g_bootloaderTree ((bootloader_api_entry_t *)*(uint32_t *)0x0020001c)

#define api_flexspi_nor_erase_sector \
    ((status_t(*)(uint32_t instance, flexspi_nor_config_t * config, uint32_t address))0x0021055d)
#define api_flexspi_nor_erase_block \
    ((status_t(*)(uint32_t instance, flexspi_nor_config_t * config, uint32_t address))0x002104a9)

/*******************************************************************************
 * Codes
 ******************************************************************************/

/*******************************************************************************
 * FlexSPI NOR driver
 ******************************************************************************/
//#if BL_FEATURE_HAS_FLEXSPI_NOR_ROMAPI
status_t flexspi_nor_flash_init(uint32_t instance, flexspi_nor_config_t *config)
{
    return g_bootloaderTree->flexSpiNorDriver->init(instance, config);
}

status_t flexspi_nor_flash_page_program(uint32_t instance,
                                        flexspi_nor_config_t *config,
                                        uint32_t dstAddr,
                                        const uint32_t *src)
{
    return g_bootloaderTree->flexSpiNorDriver->program(instance, config, dstAddr, src);
}

status_t flexspi_nor_flash_erase_all(uint32_t instance, flexspi_nor_config_t *config)
{
    // return g_bootloaderTree->flexSpiNorDriver->erase_all(instance, config);
    return kStatus_Fail; // TODO implement erase all later
}

status_t flexspi_nor_flash_erase(uint32_t instance, flexspi_nor_config_t *config, uint32_t start, uint32_t length)
{
    return g_bootloaderTree->flexSpiNorDriver->erase(instance, config, start, length);
}

status_t flexspi_nor_flash_erase_sector(uint32_t instance, flexspi_nor_config_t *config, uint32_t start)
{
    return api_flexspi_nor_erase_sector(instance, config, start);
}

status_t flexspi_nor_flash_erase_block(uint32_t instance, flexspi_nor_config_t *config, uint32_t start)
{
    return api_flexspi_nor_erase_block(instance, config, start);
}

status_t flexspi_command_xfer(uint32_t instance, flexspi_xfer_t *xfer)
{
    return g_bootloaderTree->flexSpiNorDriver->xfer(instance, xfer);
}

void flexspi_clear_cache(uint32_t instance)
{
    g_bootloaderTree->flexSpiNorDriver->clear_cache(instance);
}

//#endif // BL_FEATURE_HAS_FLEXSPI_NOR_ROMAPI
