/*
** ###################################################################
**     Processors:          MIMXRT1011CAE4A
**                          MIMXRT1011DAE5A
**
**     Compiler:            GNU C Compiler
**     Reference manual:    IMXRT1010RM Rev.A, 03/2019
**     Version:             rev. 0.1, 2019-02-14
**     Build:               b190716
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
  m_flash_config        (RX)  : ORIGIN = 0x60000400, LENGTH = 0x00000C00
  m_ivt                 (RX)  : ORIGIN = 0x60001000, LENGTH = 0x00001000
  m_interrupts          (RX)  : ORIGIN = 0x60002000, LENGTH = 0x00000400
  m_text                (RX)  : ORIGIN = 0x60002400, LENGTH = 0x00FFDC00
  m_data                (RW)  : ORIGIN = 0x20000000, LENGTH = 0x00008000 - 4 /* double tap */
  m_data2               (RW)  : ORIGIN = 0x20200000, LENGTH = 0x00010000
}

INCLUDE "rt10xx_common.ld"
