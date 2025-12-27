/*
 * Copyright 2020 NXP
 * All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

/*
 * How to setup clock using clock driver functions:
 *
 * 1. Call CLOCK_InitXXXPLL() to configure corresponding PLL clock.
 *
 * 2. Call CLOCK_InitXXXpfd() to configure corresponding PLL pfd clock.
 *
 * 3. Call CLOCK_SetRootClock() to configure corresponding module clock source and divider.
 *
 */

#include "clock_config.h"
#include "fsl_iomuxc.h"
#include "fsl_dcdc.h"
#include "fsl_pmu.h"
#include "fsl_clock.h"

/*******************************************************************************
 * Definitions
 ******************************************************************************/

/*******************************************************************************
 * Variables
 ******************************************************************************/
/* System clock frequency. */
extern uint32_t SystemCoreClock;

/*******************************************************************************
 ************************ BOARD_InitBootClocks function ************************
 ******************************************************************************/
void BOARD_InitBootClocks(void) {
    BOARD_BootClockRUN();
}

/*******************************************************************************
 ********************** Configuration BOARD_BootClockRUN ***********************
 ******************************************************************************/

/*******************************************************************************
 * Variables for BOARD_BootClockRUN configuration
 ******************************************************************************/

/* TinyUF2 runs from RAM via SDP - skip power adjustments that require
 * specific boot conditions. The LDO bypass and other power management
 * functions cause crashes when running from RAM because the power state
 * is different from XIP boot. Skip all power adjustments for TinyUF2. */
#define SKIP_DCDC_ADJUSTMENT 1
#define SKIP_FBB_ENABLE 1
#define SKIP_LDO_ADJUSTMENT 1
/* Do NOT define BYPASS_LDO_LPSR - that's what causes the crash */

const clock_arm_pll_config_t armPllConfig_BOARD_BootClockRUN = {
    .postDivider = kCLOCK_PllPostDiv2,            /* Post divider, 0 - DIV by 2, 1 - DIV by 4, 2 - DIV by 8, 3 - DIV by 1 */
    .loopDivider = 166,                           /* PLL Loop divider, Fout = Fin * ( loopDivider / ( 2 * postDivider ) ) */
};

const clock_sys_pll1_config_t sysPll1Config_BOARD_BootClockRUN = {
    .pllDiv2En = true,
};

const clock_sys_pll2_config_t sysPll2Config_BOARD_BootClockRUN = {
    .mfd = 268435455,                             /* Denominator of spread spectrum */
    .ss = NULL,                                   /* Spread spectrum parameter */
    .ssEnable = false,                            /* Enable spread spectrum or not */
};

const clock_video_pll_config_t videoPllConfig_BOARD_BootClockRUN = {
    .loopDivider = 41,                            /* PLL Loop divider, valid range for DIV_SELECT divider value: 27 ~ 54. */
    .postDivider = 0,                             /* Divider after PLL, should only be 1, 2, 4, 8, 16, 32 */
    .numerator = 1,                               /* 30 bit numerator of fractional loop divider, Fout = Fin * ( loopDivider + numerator / denominator ) */
    .denominator = 960000,                        /* 30 bit denominator of fractional loop divider, Fout = Fin * ( loopDivider + numerator / denominator ) */
    .ss = NULL,                                   /* Spread spectrum parameter */
    .ssEnable = false,                            /* Enable spread spectrum or not */
};

/*******************************************************************************
 * Code for BOARD_BootClockRUN configuration
 ******************************************************************************/
void BOARD_BootClockRUN(void) {
    clock_root_config_t rootCfg = {0};

    /* Check if we're running from flash (XIP) or RAM (SDP) */
    extern char __isr_vector[];
    uint32_t vec_addr = (uint32_t)__isr_vector;
    bool running_from_flash = (vec_addr >= 0x30000000 && vec_addr < 0x40000000);

    if (running_from_flash) {
        /* Running from flash - ROM bootloader has already configured clocks.
         * Enable oscillators needed for USB, don't touch CPU/bus clocks. */

        /* Init OSC RC 48M */
        CLOCK_OSC_EnableOsc48M(true);
        CLOCK_OSC_EnableOsc48MDiv2(true);

        /* Ensure OSC 24M is enabled - needed as reference for USB PHY PLL */
        ANADIG_OSC->OSC_24M_CTRL |= ANADIG_OSC_OSC_24M_CTRL_OSC_EN(1) |
                                    ANADIG_OSC_OSC_24M_CTRL_LP_EN(1);
        ANADIG_OSC->OSC_24M_CTRL &= ~ANADIG_OSC_OSC_24M_CTRL_OSC_24M_GATE_MASK;
        /* Wait for 24M OSC to be stable */
        while (!(ANADIG_OSC->OSC_24M_CTRL & ANADIG_OSC_OSC_24M_CTRL_OSC_24M_STABLE_MASK)) {
        }

        /* SystemCoreClock is already set by ROM - read actual clock frequency */
        SystemCoreClock = CLOCK_GetRootClockFreq(kCLOCK_Root_M7);
        return;
    }

    /* Running from RAM via SDP - do full clock configuration.
     * Use minimal clock configuration that doesn't depend on PLLs which may
     * not be properly initialized in the SDP boot context. */

    /* Config CLK_1M */
    CLOCK_OSC_Set1MHzOutputBehavior(kCLOCK_1MHzOutEnableFreeRunning1Mhz);

    /* Init OSC RC 16M */
    ANADIG_OSC->OSC_16M_CTRL |= ANADIG_OSC_OSC_16M_CTRL_EN_IRC4M16M_MASK;

    /* Init OSC RC 48M - needed for USB */
    CLOCK_OSC_EnableOsc48M(true);
    CLOCK_OSC_EnableOsc48MDiv2(true);

    /* Config OSC 24M */
    ANADIG_OSC->OSC_24M_CTRL |= ANADIG_OSC_OSC_24M_CTRL_OSC_EN(1) |
                                ANADIG_OSC_OSC_24M_CTRL_LP_EN(1) |
                                ANADIG_OSC_OSC_24M_CTRL_OSC_24M_GATE(0);
    /* Wait for 24M OSC to be stable. */
    while (ANADIG_OSC_OSC_24M_CTRL_OSC_24M_STABLE_MASK !=
           (ANADIG_OSC->OSC_24M_CTRL & ANADIG_OSC_OSC_24M_CTRL_OSC_24M_STABLE_MASK)) {
    }

    /* Configure M7 using OSC_RC_48M_DIV2 (24MHz) - slow but safe */
    rootCfg.mux = kCLOCK_M7_ClockRoot_MuxOscRc48MDiv2;
    rootCfg.div = 1;
    CLOCK_SetRootClock(kCLOCK_Root_M7, &rootCfg);

    /* Configure M7_SYSTICK using OSC_RC_48M_DIV2 */
    rootCfg.mux = kCLOCK_M7_SYSTICK_ClockRoot_MuxOscRc48MDiv2;
    rootCfg.div = 24;  /* 1MHz tick */
    CLOCK_SetRootClock(kCLOCK_Root_M7_Systick, &rootCfg);

    /* Configure BUS using OSC_RC_48M_DIV2 */
    rootCfg.mux = kCLOCK_BUS_ClockRoot_MuxOscRc48MDiv2;
    rootCfg.div = 1;
    CLOCK_SetRootClock(kCLOCK_Root_Bus, &rootCfg);

    /* Configure BUS_LPSR using OSC_RC_48M_DIV2 */
    rootCfg.mux = kCLOCK_BUS_LPSR_ClockRoot_MuxOscRc48MDiv2;
    rootCfg.div = 1;
    CLOCK_SetRootClock(kCLOCK_Root_Bus_Lpsr, &rootCfg);

    /* Configure CSSYS using OSC_RC_48M_DIV2 */
    rootCfg.mux = kCLOCK_CSSYS_ClockRoot_MuxOscRc48MDiv2;
    rootCfg.div = 1;
    CLOCK_SetRootClock(kCLOCK_Root_Cssys, &rootCfg);

    /* Configure FLEXSPI1 using OSC_RC_48M_DIV2 */
    rootCfg.mux = kCLOCK_FLEXSPI1_ClockRoot_MuxOscRc48MDiv2;
    rootCfg.div = 1;
    CLOCK_SetRootClock(kCLOCK_Root_Flexspi1, &rootCfg);

    /* Configure GPT1 using OSC_24M for timing */
    rootCfg.mux = kCLOCK_GPT1_ClockRoot_MuxOsc24MOut;
    rootCfg.div = 1;
    CLOCK_SetRootClock(kCLOCK_Root_Gpt1, &rootCfg);

    /* Update SystemCoreClock - we're running at 24MHz */
    SystemCoreClock = 24000000UL;
}
