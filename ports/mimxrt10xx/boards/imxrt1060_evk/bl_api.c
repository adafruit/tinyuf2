/*
 * Copyright 2017-2020 NXP
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

/*******************************************************************************
 * Codes
 ******************************************************************************/

/*******************************************************************************
 * RTWDOG driver
 ******************************************************************************/
void RTWDOG_ClearStatusFlags(RTWDOG_Type *base, uint32_t mask)
{
    g_bootloaderTree->rtwdogDriver->RTWDOG_ClearStatusFlags(base, mask);
}

void RTWDOG_GetDefaultConfig(rtwdog_config_t *config)
{
    g_bootloaderTree->rtwdogDriver->RTWDOG_GetDefaultConfig(config);
}

void RTWDOG_Init(RTWDOG_Type *base, const rtwdog_config_t *config)
{
    g_bootloaderTree->rtwdogDriver->RTWDOG_Init(base, config);
}

void RTWDOG_Deinit(RTWDOG_Type *base)
{
    g_bootloaderTree->rtwdogDriver->RTWDOG_Deinit(base);
}

/*******************************************************************************
 * WDOG driver
 ******************************************************************************/

void WDOG_GetDefaultConfig(wdog_config_t *config)
{
    g_bootloaderTree->wdogDriver->WDOG_GetDefaultConfig(config);
}

void WDOG_Init(WDOG_Type *base, const wdog_config_t *config)
{
    g_bootloaderTree->wdogDriver->WDOG_Init(base, config);
}

void WDOG_Deinit(WDOG_Type *base)
{
    g_bootloaderTree->wdogDriver->WDOG_Deinit(base);
}

uint16_t WDOG_GetStatusFlags(WDOG_Type *base)
{
    return g_bootloaderTree->wdogDriver->WDOG_GetStatusFlags(base);
}

void WDOG_ClearInterruptStatus(WDOG_Type *base, uint16_t mask)
{
    g_bootloaderTree->wdogDriver->WDOG_ClearInterruptStatus(base, mask);
}

void WDOG_Refresh(WDOG_Type *base)
{
    g_bootloaderTree->wdogDriver->WDOG_Refresh(base);
}

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
    return g_bootloaderTree->flexSpiNorDriver->erase_all(instance, config);
}

status_t flexspi_nor_get_config(uint32_t instance, flexspi_nor_config_t *config, serial_nor_config_option_t *option)
{
    status_t status = g_bootloaderTree->flexSpiNorDriver->get_config(instance, config, option);

    if (status == kStatus_Success)
    {
        if (config->memConfig.readSampleClkSrc == kFlexSPIReadSampleClk_LoopbackInternally)
        {
            if (option->option0.B.misc_mode != kSerialNorEnhanceMode_InternalLoopback)
            {
                config->memConfig.readSampleClkSrc = kFlexSPIReadSampleClk_LoopbackFromDqsPad;
            }
        }

        if (option->option0.B.option_size)
        {
            // A workaround to support drive strength configuration using Flash APIs
            if (option->option1.B.drive_strength)
            {
                flexspi_update_padsetting(&config->memConfig, option->option1.B.drive_strength);
            }

            // A workaround to support parallel mode using Flash APIs
            if (option->option1.B.flash_connection == kSerialNorConnection_Parallel)
            {
                config->memConfig.controllerMiscOption |= FLEXSPI_BITMASK(kFlexSpiMiscOffset_ParallelEnable);
                config->pageSize *= 2;
                config->sectorSize *= 2;
                config->blockSize *= 2;
                config->memConfig.sflashB1Size = config->memConfig.sflashA1Size;
            }
        }
    }

    return status;
}

status_t flexspi_nor_flash_erase(uint32_t instance, flexspi_nor_config_t *config, uint32_t start, uint32_t length)
{
    return g_bootloaderTree->flexSpiNorDriver->erase(instance, config, start, length);
}

status_t flexspi_nor_flash_read(
    uint32_t instance, flexspi_nor_config_t *config, uint32_t *dst, uint32_t start, uint32_t bytes)
{
    return g_bootloaderTree->flexSpiNorDriver->read(instance, config, dst, start, bytes);
}

void flexspi_clear_cache(uint32_t instance)
{
    g_bootloaderTree->flexSpiNorDriver->clear_cache(instance);
}

status_t flexspi_command_xfer(uint32_t instance, flexspi_xfer_t *xfer)
{
    return g_bootloaderTree->flexSpiNorDriver->xfer(instance, xfer);
}

//!@brief Configure FlexSPI Lookup table
status_t flexspi_update_lut(uint32_t instance, uint32_t seqIndex, const uint32_t *lutBase, uint32_t numberOfSeq)
{
    return g_bootloaderTree->flexSpiNorDriver->update_lut(instance, seqIndex, lutBase, numberOfSeq);
}

//#endif // BL_FEATURE_HAS_FLEXSPI_NOR_ROMAPI
