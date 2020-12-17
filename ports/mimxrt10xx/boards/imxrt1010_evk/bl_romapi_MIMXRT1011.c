/*
 * Copyright 2016-2020 NXP
 *
 * All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

// Functions from ROM are applied so as to reduce Flashloader's binary size

#include "bl_flexspi.h"
#include "bl_trng.h"
#include "flexspi_nor_flash.h"
#include "fsl_clock.h"
#include "fsl_lpuart.h"

/*****************************************************************************************************/
/*                                         LPUART APIs                                               */
/*****************************************************************************************************/
/*
status_t LPUART_WriteBlocking(LPUART_Type *base, const uint8_t *data, size_t length)
{
    void (*const _LPUART_WriteBlocking)(LPUART_Type *, const uint8_t *, size_t) =
        (void (*)(LPUART_Type *, const uint8_t *, size_t))0x0020904b;
    _LPUART_WriteBlocking(base, data, length);
    return kStatus_Success;
}

void LPUART_Deinit(LPUART_Type *base)
{
    void (*const _LPUART_Deinit)(LPUART_Type *) = (void (*)(LPUART_Type *))0x00208da7;
    _LPUART_Deinit(base);
}

void LPUART_GetDefaultConfig(lpuart_config_t *config)
{
    void (*const _LPUART_GetDefaultConfig)(lpuart_config_t *) = (void (*)(lpuart_config_t *))0x00208e0b;
    _LPUART_GetDefaultConfig(config);
}

status_t LPUART_Init(LPUART_Type *base, const lpuart_config_t *config, uint32_t srcClock_Hz)
{
    static LPUART_Type *const s_lpuartBases[] = LPUART_BASE_PTRS;
    static const clock_ip_name_t s_lpuartClock[] = LPUART_CLOCKS;

    void (*const _LPUART_Init)(LPUART_Type *, const lpuart_config_t *, uint32_t) =
        (void (*)(LPUART_Type *, const lpuart_config_t *, uint32_t))0x00208e31;

    uint32_t instance;
    // Find the instance index from base address mappings. 
    for (instance = 0; instance < FSL_FEATURE_SOC_LPUART_COUNT; instance++)
    {
        if (s_lpuartBases[instance] == base)
        {
            break;
        }
    }
    assert(instance < FSL_FEATURE_SOC_LPUART_COUNT);

    CLOCK_EnableClock(s_lpuartClock[instance]);
    _LPUART_Init(base, config, srcClock_Hz);
    return kStatus_Success;
}

void LPUART_EnableInterrupts(LPUART_Type *base, uint32_t mask)
{
    void (*const _LPUART_EnableInterrupts)(LPUART_Type *, uint32_t) = (void (*)(LPUART_Type *, uint32_t))0x00208dbb;
    _LPUART_EnableInterrupts(base, mask);
}

uint32_t LPUART_GetStatusFlags(LPUART_Type *base)
{
    uint32_t (*const _LPUART_GetStatusFlags)(LPUART_Type *) = (uint32_t(*)(LPUART_Type *))0x00208e21;
    return _LPUART_GetStatusFlags(base);
}
*/
/*****************************************************************************************************/
/*                                        FlexSPI APIs                                               */
/*****************************************************************************************************/
bool flexspi_is_parallel_mode(flexspi_mem_config_t *config)
{
    bool (*const _flexspi_is_parallel_mode)(flexspi_mem_config_t *) = (bool (*)(flexspi_mem_config_t *))0x0020c687;
    return _flexspi_is_parallel_mode(config);
}

status_t flexspi_device_wait_busy(uint32_t instance,
                                  flexspi_mem_config_t *config,
                                  bool isParallelMode,
                                  uint32_t baseAddr)
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

status_t flexspi_device_write_enable(uint32_t instance,
                                     flexspi_mem_config_t *config,
                                     bool isParallelMode,
                                     uint32_t baseAddr)
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

/*****************************************************************************************************/
/*                                          TRNG APIs                                                */
/*****************************************************************************************************/
status_t TRNG_GetDefaultConfig(trng_config_t *userConfig)
{
    status_t (*const _TRNG_GetDefaultConfig)(trng_config_t *) = (status_t(*)(trng_config_t *))0x002092d9;
    return _TRNG_GetDefaultConfig(userConfig);
}

status_t TRNG_Init(TRNG_Type *base, const trng_config_t *userConfig)
{
    status_t (*const _TRNG_Init)(TRNG_Type *, const trng_config_t *) =
        (status_t(*)(TRNG_Type *, const trng_config_t *))0x002093df;
    return _TRNG_Init(base, userConfig);
}

status_t TRNG_GetRandomData(TRNG_Type *base, void *data, size_t dataSize)
{
    status_t (*const _TRNG_GetRandomData)(TRNG_Type *, void *, size_t) =
        (status_t(*)(TRNG_Type *, void *, size_t))0x0020935d;
    return _TRNG_GetRandomData(base, data, dataSize);
}

/*****************************************************************************************************/
/*                                          Clocking APIs                                                */
/*****************************************************************************************************/
void clock_setup(void)
{
#define _SystemCoreClock (*(const uint32_t *)0x20203a00)
    void (*const _clock_setup)(void) = (void (*)(void))0x0020cf67;
    _clock_setup();
    SystemCoreClock = _SystemCoreClock;
}

status_t flexspi_get_clock(uint32_t instance, flexspi_clock_type_t type, uint32_t *freq)
{
    status_t (*const _flexspi_get_clock)(uint32_t, flexspi_clock_type_t, uint32_t *) =
        (status_t(*)(uint32_t, flexspi_clock_type_t, uint32_t *))0x0020c225;
    return _flexspi_get_clock(instance, type, freq);
}
