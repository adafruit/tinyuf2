/*
** ###################################################################
**     Processors:          MIMXRT1021CAF4A
**                          MIMXRT1021CAG4A
**                          MIMXRT1021DAF5A
**                          MIMXRT1021DAG5A
**
**     Compiler:            GNU C Compiler
**     Reference manual:    IMXRT1020RM Rev. 1RC, 05/2018
**     Version:             rev. 0.1, 2017-06-06
**     Build:               b180801
**
**     Abstract:
**         Linker file for the GNU C Compiler
**
**     Copyright 2016 Freescale Semiconductor, Inc.
**     Copyright 2016-2018 NXP
**
**     SPDX-License-Identifier: BSD-3-Clause
**
**     http:                 www.nxp.com
**     mail:                 support@nxp.com
**
** ###################################################################
*/

/* Specify the memory areas */
MEMORY
{
  m_flash_config        (RX)  : ORIGIN = 0x60000000, LENGTH = 0x00001000
  m_ivt                 (RX)  : ORIGIN = 0x60001000, LENGTH = 0x00001000
  m_interrupts          (RX)  : ORIGIN = 0x60002000, LENGTH = 0x00000400
  m_text                (RX)  : ORIGIN = 0x60002400, LENGTH = 0x007FDC00
  m_data                (RW)  : ORIGIN = 0x20000000, LENGTH = 0x00010000 - 4 /* double tap */
  m_data2               (RW)  : ORIGIN = 0x20200000, LENGTH = 0x00020000
}

INCLUDE "rt10xx_common.ld"
