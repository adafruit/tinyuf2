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
#include "fsl_clock.h"
#include "fsl_device_registers.h"
#include "fsl_rtwdog.h"
#include "fsl_wdog.h"

/*******************************************************************************
 * Definitions
 ******************************************************************************/
typedef struct
{
    uint32_t version;
    status_t (*init)(uint32_t instance, flexspi_nor_config_t *config);
    status_t (*program)(uint32_t instance, flexspi_nor_config_t *config, uint32_t dst_addr, const uint32_t *src);
    status_t (*erase_all)(uint32_t instance, flexspi_nor_config_t *config);
    status_t (*erase)(uint32_t instance, flexspi_nor_config_t *config, uint32_t start, uint32_t lengthInBytes);
    status_t (*read)(uint32_t instance, flexspi_nor_config_t *config, uint32_t *dst, uint32_t addr, uint32_t lengthInBytes);
    void (*clear_cache)(uint32_t instance);
    status_t (*xfer)(uint32_t instance, flexspi_xfer_t *xfer);
    status_t (*update_lut)(uint32_t instance, uint32_t seqIndex, const uint32_t *lutBase, uint32_t seqNumber);
    status_t (*get_config)(uint32_t instance, flexspi_nor_config_t *config, serial_nor_config_option_t *option);
} flexspi_nor_driver_interface_t;

typedef struct
{
    uint32_t version;
    void (*CLOCK_SetMux)(clock_mux_t mux, uint32_t value);
    uint32_t (*CLOCK_GetMux)(clock_mux_t mux);
    void (*CLOCK_SetDiv)(clock_div_t divider, uint32_t value);
    uint32_t (*CLOCK_GetDiv)(clock_div_t divider);
    void (*CLOCK_ControlGate)(clock_ip_name_t name, clock_gate_value_t value);
    void (*CLOCK_EnableClock)(clock_ip_name_t name);
    void (*CLOCK_DisableClock)(clock_ip_name_t name);
    void (*CLOCK_SetMode)(clock_mode_t mode);
    void (*CLOCK_SetPllBypass)(CCM_ANALOG_Type *base, clock_pll_t pll, bool bypass);
    uint32_t (*CLOCK_GetFreq)(clock_name_t name);
    uint32_t (*CLOCK_GetCpuClkFreq)(void);
    void (*CLOCK_InitExternalClk)(bool bypassXtalOsc);
    void (*CLOCK_DeinitExternalClk)(void);
    void (*CLOCK_SwitchOsc)(clock_osc_t osc);
    uint32_t (*CLOCK_GetRtcFreq)(void);
    void (*CLOCK_SetXtalFreq)(uint32_t freq);
    void (*CLOCK_SetRtcXtalFreq)(uint32_t freq);
    void (*CLOCK_InitRcOsc24M)(void);
    void (*CLOCK_DeinitRcOsc24M)(void);
    void (*CLOCK_InitArmPll)(const clock_arm_pll_config_t *config);
    void (*CLOCK_DeinitArmPll)(void);
    void (*CLOCK_InitSysPll)(const clock_sys_pll_config_t *config);
    void (*CLOCK_DeinitSysPll)(void);
    void (*CLOCK_InitUsb1Pll)(const clock_usb_pll_config_t *config);
    void (*CLOCK_DeinitUsb1Pll)(void);
    void (*CLOCK_InitUsb2Pll)(const clock_usb_pll_config_t *config);
    void (*CLOCK_DeinitUsb2Pll)(void);
    void (*CLOCK_InitAudioPll)(const clock_audio_pll_config_t *config);
    void (*CLOCK_DeinitAudioPll)(void);
    void (*CLOCK_InitVideoPll)(const clock_video_pll_config_t *config);
    void (*CLOCK_DeinitVideoPll)(void);
    void (*CLOCK_InitEnetPll)(const clock_enet_pll_config_t *config);
    void (*CLOCK_DeinitEnetPll)(void);
    uint32_t (*CLOCK_GetPllFreq)(clock_pll_t pll);
    void (*CLOCK_InitSysPfd)(clock_pfd_t pfd, uint8_t pfdFrac);
    void (*CLOCK_DeinitSysPfd)(clock_pfd_t pfd);
    void (*CLOCK_InitUsb1Pfd)(clock_pfd_t pfd, uint8_t pfdFrac);
    void (*CLOCK_DeinitUsb1Pfd)(clock_pfd_t pfd);
    uint32_t (*CLOCK_GetSysPfdFreq)(clock_pfd_t pfd);
    uint32_t (*CLOCK_GetUsb1PfdFreq)(clock_pfd_t pfd);
    bool (*CLOCK_EnableUsbhs0Clock)(clock_usb_src_t src, uint32_t freq);
    bool (*CLOCK_EnableUsbhs0PhyPllClock)(clock_usb_phy_src_t src, uint32_t freq);
    void (*CLOCK_DisableUsbhs0PhyPllClock)(void);
    bool (*CLOCK_EnableUsbhs1Clock)(clock_usb_src_t src, uint32_t freq);
    bool (*CLOCK_EnableUsbhs1PhyPllClock)(clock_usb_phy_src_t src, uint32_t freq);
    void (*CLOCK_DisableUsbhs1PhyPllClock)(void);
} clock_driver_interface_t;

typedef struct
{
    void (*RTWDOG_GetDefaultConfig)(rtwdog_config_t *config);
    void (*RTWDOG_Init)(RTWDOG_Type *base, const rtwdog_config_t *config);
    void (*RTWDOG_Deinit)(RTWDOG_Type *base);
    void (*RTWDOG_Enable)(RTWDOG_Type *base);
    void (*RTWDOG_Disable)(RTWDOG_Type *base);
    void (*RTWDOG_EnableInterrupts)(RTWDOG_Type *base, uint32_t mask);
    void (*RTWDOG_DisableInterrupts)(RTWDOG_Type *base, uint32_t mask);
    uint32_t (*RTWDOG_GetStatusFlags)(RTWDOG_Type *base);
    void (*RTWDOG_ClearStatusFlags)(RTWDOG_Type *base, uint32_t mask);
    void (*RTWDOG_SetTimeoutValue)(RTWDOG_Type *base, uint16_t timeoutCount);
    void (*RTWDOG_SetWindowValue)(RTWDOG_Type *base, uint16_t windowValue);
    void (*RTWDOG_Unlock)(RTWDOG_Type *base);
    void (*RTWDOG_Refresh)(RTWDOG_Type *base);
    uint16_t (*RTWDOG_GetCounterValue)(RTWDOG_Type *base);
} rtwdog_driver_interface_t;

typedef struct
{
    void (*WDOG_GetDefaultConfig)(wdog_config_t *config);
    void (*WDOG_Init)(WDOG_Type *base, const wdog_config_t *config);
    void (*WDOG_Deinit)(WDOG_Type *base);
    void (*WDOG_Enable)(WDOG_Type *base);
    void (*WDOG_Disable)(WDOG_Type *base);
    void (*WDOG_EnableInterrupts)(WDOG_Type *base, uint16_t mask);
    uint16_t (*WDOG_GetStatusFlags)(WDOG_Type *base);
    void (*WDOG_ClearInterruptStatus)(WDOG_Type *base, uint16_t mask);
    void (*WDOG_SetTimeoutValue)(WDOG_Type *base, uint16_t timeoutCount);
    void (*WDOG_SetInterrputTimeoutValue)(WDOG_Type *base, uint16_t timeoutCount);
    void (*WDOG_DisablePowerDownEnable)(WDOG_Type *base);
    void (*WDOG_Refresh)(WDOG_Type *base);
} wdog_driver_interface_t;

typedef struct
{
    const uint32_t version;                                 //!< Bootloader version number
    const char *copyright;                                  //!< Bootloader Copyright
    void (*runBootloader)(void *arg);                       //!< Function to start the bootloader executing
    const uint32_t *reserved0;                              //!< Reserved
    const flexspi_nor_driver_interface_t *flexSpiNorDriver; //!< FlexSPI NOR Flash API
    const uint32_t *reserved1;                              //!< Reserved
    const clock_driver_interface_t *clockDriver;
    const rtwdog_driver_interface_t *rtwdogDriver;
    const wdog_driver_interface_t *wdogDriver;
    const uint32_t *reserved2;
} bootloader_api_entry_t;

enum
{
    kEnterBootloader_Tag = 0xEB,
    kEnterBootloader_Mode_Default = 0,
    kEnterBootloader_Mode_SerialDownloader = 1,

    kEnterBootloader_SerialInterface_Auto = 0,
    kEnterBootloader_SerialInterface_USB = 1,
    kEnterBootloader_SerialInterface_UART = 2,

    kEnterBootloader_ImageIndex_Max = 3,
};

enum
{
    kFlexSpiNorDriver_Version_1_5 = MAKE_VERSION(1, 5, 0),
};

typedef union {
    struct
    {
        uint32_t imageIndex : 4;
        uint32_t reserved : 12;
        uint32_t serialBootInterface : 4;
        uint32_t bootMode : 4;
        uint32_t tag : 8;
    } B;
    uint32_t U;
} run_bootloader_ctx_t;

#endif //__BL_API_H__
