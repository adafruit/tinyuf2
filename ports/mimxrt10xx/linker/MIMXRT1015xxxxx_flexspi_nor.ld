/*
** ###################################################################
**     Processors:          MIMXRT1015CAF4A
**                          MIMXRT1015DAF5A
**
**     Compiler:            GNU C Compiler
**     Reference manual:    IMXRT1015RM Rev.0, 12/2018
**     Version:             rev. 1.0, 2019-01-18
**     Build:               b190118
**
**     Abstract:
**         Linker file for the GNU C Compiler
**
**     Copyright 2016 Freescale Semiconductor, Inc.
**     Copyright 2016-2019 NXP
**     All rights reserved.
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
  m_text                (RX)  : ORIGIN = 0x60002400, LENGTH = 0x00FFDC00
  m_data                (RW)  : ORIGIN = 0x20000000, LENGTH = 0x00008000 - 4 /* double tap */
  m_data2               (RW)  : ORIGIN = 0x20200000, LENGTH = 0x00010000
}

INCLUDE "rt10xx_common.ld"
