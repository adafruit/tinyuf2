/*
 * Copyright 2017 NXP
 * All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#include "flexspi_nor_flash.h"
#include "fsl_flexspi_nor_boot.h"
#include "boards.h"

#if 1
// Config for IS25WP064A with QSPI after changing resistors to send signal to
// QSPI instead of hyper flash!
__attribute__((section(".boot_hdr.conf"))) const flexspi_nor_config_t qspiflash_config = {
  .pageSize           = 256u,
  .sectorSize         = 4u * 1024u,
  .ipcmdSerialClkFreq = kFlexSpiSerialClk_30MHz,
  .blockSize          = 0x00010000,
  .isUniformBlockSize = false,
  .memConfig =
    {
      .tag              = FLEXSPI_CFG_BLK_TAG,
      .version          = FLEXSPI_CFG_BLK_VERSION,
      .readSampleClkSrc = kFlexSPIReadSampleClk_LoopbackFromSckPad,
      .csHoldTime       = 3u,
      .csSetupTime      = 3u,

      .busyOffset      = 0u, // Status bit 0 indicates busy.
      .busyBitPolarity = 0u, // Busy when the bit is 1.

      .deviceModeCfgEnable = 1u,
      .deviceModeType      = kDeviceConfigCmdType_QuadEnable,
      .deviceModeSeq =
        {
          .seqId  = 4u,
          .seqNum = 1u,
        },
      .deviceModeArg = 0x40,
      .deviceType    = kFlexSpiDeviceType_SerialNOR,
      .sflashPadType = kSerialFlash_4Pads,
      .serialClkFreq = kFlexSpiSerialClk_133MHz,
      .sflashA1Size  = FLASH_SIZE,
      .lookupTable =
        {// FLEXSPI_LUT_SEQ(cmd0, pad0, op0, cmd1, pad1, op1)
         // The high 16 bits is command 1 and the low are command 0.
         // Within a command, the top 6 bits are the opcode, the next two are the number
         // of pads and then last byte is the operand. The operand's meaning changes
         // per opcode.

         // Indices with ROM should always have the same function because the ROM
         // bootloader uses it.

         // 0: ROM: Read LUTs
         // Quad version
         SEQUENCE(FLEXSPI_LUT_SEQ(CMD_SDR, FLEXSPI_1PAD, 0xEB /* the command to send */, RADDR_SDR, FLEXSPI_4PAD,
                                  24 /* bits to transmit */),
                  FLEXSPI_LUT_SEQ(DUMMY_SDR, FLEXSPI_4PAD, 6 /* 6 dummy cycles, 2 for M7-0 and 4 dummy */, READ_SDR,
                                  FLEXSPI_4PAD, 0x04),
                  // Single fast read version, good for debugging.
                  // FLEXSPI_LUT_SEQ(CMD_SDR,   FLEXSPI_1PAD, 0x0B /* the command to send */,
                  //                 RADDR_SDR, FLEXSPI_1PAD, 24  /* bits to transmit */),
                  // FLEXSPI_LUT_SEQ(DUMMY_SDR, FLEXSPI_1PAD, 8 /* 8 dummy clocks */,
                  //                 READ_SDR,  FLEXSPI_1PAD, 0x04),
                  TWO_EMPTY_STEPS, TWO_EMPTY_STEPS),

         // 1: ROM: Read status
         SEQUENCE(FLEXSPI_LUT_SEQ(CMD_SDR, FLEXSPI_1PAD, 0x05 /* the command to send */, READ_SDR, FLEXSPI_1PAD, 0x02),
                  TWO_EMPTY_STEPS, TWO_EMPTY_STEPS, TWO_EMPTY_STEPS),

         // 2: Empty
         EMPTY_SEQUENCE,

         // 3: ROM: Write Enable
         SEQUENCE(FLEXSPI_LUT_SEQ(CMD_SDR, FLEXSPI_1PAD, 0x06 /* the command to send */, STOP, FLEXSPI_1PAD, 0x00),
                  TWO_EMPTY_STEPS, TWO_EMPTY_STEPS, TWO_EMPTY_STEPS),

         // 4: Config: Write Status
         SEQUENCE(FLEXSPI_LUT_SEQ(CMD_SDR, FLEXSPI_1PAD, 0x01 /* the command to send */, WRITE_SDR, FLEXSPI_1PAD, 0x01),
                  TWO_EMPTY_STEPS, TWO_EMPTY_STEPS, TWO_EMPTY_STEPS),

         // 5: ROM: Erase Sector
         SEQUENCE(FLEXSPI_LUT_SEQ(CMD_SDR, FLEXSPI_1PAD, 0x20 /* the command to send */, RADDR_SDR, FLEXSPI_1PAD,
                                  24 /* bits to transmit */),
                  TWO_EMPTY_STEPS, TWO_EMPTY_STEPS, TWO_EMPTY_STEPS),

         // 6: Empty
         EMPTY_SEQUENCE,

         // 7: Empty
         EMPTY_SEQUENCE,

         // 8: Block Erase
         SEQUENCE(FLEXSPI_LUT_SEQ(CMD_SDR, FLEXSPI_1PAD, 0xD8 /* the command to send */, RADDR_SDR, FLEXSPI_1PAD,
                                  24 /* bits to transmit */),
                  TWO_EMPTY_STEPS, TWO_EMPTY_STEPS, TWO_EMPTY_STEPS),

         // 9: ROM: Page program
         SEQUENCE(FLEXSPI_LUT_SEQ(CMD_SDR, FLEXSPI_1PAD, 0x02 /* the command to send */, RADDR_SDR, FLEXSPI_1PAD,
                                  24 /* bits to transmit */),

                  FLEXSPI_LUT_SEQ(WRITE_SDR, FLEXSPI_1PAD, 0x04 /* data out */, STOP, FLEXSPI_1PAD, 0), TWO_EMPTY_STEPS,
                  TWO_EMPTY_STEPS),

         // 10: Empty
         EMPTY_SEQUENCE,

         // 11: ROM: Chip erase
         SEQUENCE(FLEXSPI_LUT_SEQ(CMD_SDR, FLEXSPI_1PAD, 0x60 /* the command to send */, STOP, FLEXSPI_1PAD, 0),
                  TWO_EMPTY_STEPS, TWO_EMPTY_STEPS, TWO_EMPTY_STEPS),

         // 12: Empty
         EMPTY_SEQUENCE,

         // 13: ROM: Read SFDP
         EMPTY_SEQUENCE,

         // 14: ROM: Restore no cmd
         EMPTY_SEQUENCE,

         // 15: ROM: Dummy
         EMPTY_SEQUENCE},
    },
};

#else
// hyperflash
__attribute__((section(".boot_hdr.conf"))) const flexspi_nor_config_t qspiflash_config = {
  .memConfig =
    {
      .tag                = FLEXSPI_CFG_BLK_TAG,
      .version            = FLEXSPI_CFG_BLK_VERSION,
      .readSampleClkSrc   = kFlexSPIReadSampleClk_ExternalInputFromDqsPad,
      .csHoldTime         = 3u,
      .csSetupTime        = 3u,
      .columnAddressWidth = 3u,
      // Enable DDR mode, Wordaddassable, Safe configuration, Differential clock
      .controllerMiscOption =
        (1u << kFlexSpiMiscOffset_DdrModeEnable) | (1u << kFlexSpiMiscOffset_WordAddressableEnable) |
        (1u << kFlexSpiMiscOffset_SafeConfigFreqEnable) | (1u << kFlexSpiMiscOffset_DiffClkEnable),
      .sflashPadType = kSerialFlash_8Pads,
      .serialClkFreq = kFlexSpiSerialClk_133MHz,
      .sflashA1Size  = 64u * 1024u * 1024u,
      .dataValidTime = {16u, 16u},
      .lookupTable =
        {
          // Read LUTs
          FLEXSPI_LUT_SEQ(CMD_DDR, FLEXSPI_8PAD, 0xA0, RADDR_DDR, FLEXSPI_8PAD, 0x18),
          FLEXSPI_LUT_SEQ(CADDR_DDR, FLEXSPI_8PAD, 0x10, DUMMY_DDR, FLEXSPI_8PAD, 0x06),
          FLEXSPI_LUT_SEQ(READ_DDR, FLEXSPI_8PAD, 0x04, STOP, FLEXSPI_1PAD, 0x0),
        },
    },
  .pageSize           = 512u,
  .sectorSize         = 256u * 1024u,
  .blockSize          = 256u * 1024u,
  .isUniformBlockSize = true,
};
#endif
