/*
** ###################################################################
**     Processors:          MIMXRT1064CVJ5A
**                          MIMXRT1064CVL5A
**                          MIMXRT1064DVJ6A
**                          MIMXRT1064DVL6A
**
**     Compiler:            GNU C Compiler
**     Reference manual:    IMXRT1064RM Rev.0.1, 12/2018
**     Version:             rev. 0.1, 2018-06-22
**     Build:               b190226
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
  m_flash_config        (RX)  : ORIGIN = 0x70000000, LENGTH = 0x00001000
  m_ivt                 (RX)  : ORIGIN = 0x70001000, LENGTH = 0x00001000
  m_interrupts          (RX)  : ORIGIN = 0x70002000, LENGTH = 0x00000400
  m_text                (RX)  : ORIGIN = 0x70002400, LENGTH = 0x003FDC00
  m_data                (RW)  : ORIGIN = 0x20000000, LENGTH = 0x00020000
  m_data2               (RW)  : ORIGIN = 0x20200000, LENGTH = 0x000C0000
}

INCLUDE "rt10xx_common.ld"
