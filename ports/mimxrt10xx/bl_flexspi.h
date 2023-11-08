/*
 * Copyright 2014-2015 Freescale Semiconductor, Inc.
 * Copyright 2016-2019 NXP
 * All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 */

#ifndef __FSL_FLEXSPI_H__
#define __FSL_FLEXSPI_H__

#include "fsl_common.h"

/**********************************************************************************************************************
 * Definitions
 *********************************************************************************************************************/
/* The count of FlexSPI_LUT */
#define FlexSPI_LUT_COUNT (64)
/* The count of FlexSPI AHB Buffer */
#define FlexSPI_AHB_RX_BUF_COUNT (4U)
/* AHB RX_BUF depth, in longwords */
#define FlexSPI_AHB_RX_BUF_DEPTH (512U)
/* AHB TX BUF depth, in longwords */
#define FlexSPI_AHB_TX_BUF_DEPTH (32U)
/* IP_RX_BUF depth, in longwords */
#define FlexSPI_IP_RX_BUF_DEPTH (256U)
/* IP TX BUF depth, in longwords */
#define FlexSPI_IP_TX_BUF_DEPTH (256U)

/* FLEXSPI memory config block related definitions */
#define FLEXSPI_CFG_BLK_TAG (0x42464346UL)     // ascii "FCFB" Big Endian
#define FLEXSPI_CFG_BLK_VERSION (0x56010400UL) // V1.4.0
#define FLEXSPI_CFG_BLK_SIZE (512)

/* FLEXSPI Feature related definitions */
#define FLEXSPI_FEATURE_HAS_PARALLEL_MODE 1

/* Lookup table related definitions */
#define CMD_INDEX_READ 0
#define CMD_INDEX_READSTATUS 1
#define CMD_INDEX_WRITEENABLE 2
#define CMD_INDEX_WRITE 4

#define CMD_LUT_SEQ_IDX_READ 0
#define CMD_LUT_SEQ_IDX_READSTATUS 1
#define CMD_LUT_SEQ_IDX_WRITEENABLE 3
#define CMD_LUT_SEQ_IDX_WRITE 9

#define CMD_SDR 0x01
#define CMD_DDR 0x21
#define RADDR_SDR 0x02
#define RADDR_DDR 0x22
#define CADDR_SDR 0x03
#define CADDR_DDR 0x23
#define MODE1_SDR 0x04
#define MODE1_DDR 0x24
#define MODE2_SDR 0x05
#define MODE2_DDR 0x25
#define MODE4_SDR 0x06
#define MODE4_DDR 0x26
#define MODE8_SDR 0x07
#define MODE8_DDR 0x27
#define WRITE_SDR 0x08
#define WRITE_DDR 0x28
#define READ_SDR 0x09
#define READ_DDR 0x29
#define LEARN_SDR 0x0A
#define LEARN_DDR 0x2A
#define DATSZ_SDR 0x0B
#define DATSZ_DDR 0x2B
#define DUMMY_SDR 0x0C
#define DUMMY_DDR 0x2C
#define DUMMY_RWDS_SDR 0x0D
#define DUMMY_RWDS_DDR 0x2D
#define JMP_ON_CS 0x1F
#define STOP 0

#define FLEXSPI_1PAD 0
#define FLEXSPI_2PAD 1
#define FLEXSPI_4PAD 2
#define FLEXSPI_8PAD 3

#define FLEXSPI_LUT_SEQ(cmd0, pad0, op0, cmd1, pad1, op1)                                                              \
    (FLEXSPI_LUT_OPERAND0(op0) | FLEXSPI_LUT_NUM_PADS0(pad0) | FLEXSPI_LUT_OPCODE0(cmd0) | FLEXSPI_LUT_OPERAND1(op1) | \
     FLEXSPI_LUT_NUM_PADS1(pad1) | FLEXSPI_LUT_OPCODE1(cmd1))

//!@brief Definitions for FlexSPI Serial Clock Frequency
typedef enum _FlexSpiSerialClockFreq
{
    kFlexSpiSerialClk_30MHz  = 1,
    kFlexSpiSerialClk_50MHz  = 2,
    kFlexSpiSerialClk_60MHz  = 3,
    kFlexSpiSerialClk_75MHz  = 4,
    kFlexSpiSerialClk_80MHz  = 5,
    kFlexSpiSerialClk_100MHz = 6,

#if defined(MIMXRT1011_SERIES) || defined(MIMXRT1176_cm7_SERIES) || defined(MIMXRT1042_SERIES) || defined(MIMXRT1064_SERIES) || defined(MIMXRT1062_SERIES)
    kFlexSpiSerialClk_120MHz = 7,
    kFlexSpiSerialClk_133MHz = 8,
    kFlexSpiSerialClk_166MHz = 9,
#elif defined(MIMXRT1015_SERIES) || defined(MIMXRT1021_SERIES) || defined(MIMXRT1024_SERIES) || defined(MIMXRT1052_SERIES)
    kFlexSpiSerialClk_133MHz = 7,
    kFlexSpiSerialClk_166MHz = 8,
    kFlexSpiSerialClk_200MHz = 9,
#else
  #error This series is not supported
#endif
} flexspi_serial_clk_freq_t;

//!@brief Definitions for FlexSPI Serial Clock Frequency
typedef enum _FlexSpiSerialClockSafeFreq
{
    kFlexSpiSerialClk_SafeFreq = 1,
} flexspi_serial_clk_safe_freq_t;

//!@brief FlexSPI clock configuration type
enum
{
    kFlexSpiClk_SDR, //!< Clock configure for SDR mode
    kFlexSpiClk_DDR, //!< Clock configurat for DDR mode
};

//!@brief FlexSPI Read Sample Clock Source definition
typedef enum _FlashReadSampleClkSource
{
    kFlexSPIReadSampleClk_LoopbackInternally      = 0,
    kFlexSPIReadSampleClk_LoopbackFromDqsPad      = 1,
    kFlexSPIReadSampleClk_LoopbackFromSckPad      = 2,
    kFlexSPIReadSampleClk_ExternalInputFromDqsPad = 3,
} flexspi_read_sample_clk_t;

//!@brief FlexSPI IP Error codes
typedef enum _FlexSpiIpCmdError
{
    kFlexSpiIpCmdError_NoError = 0,
    kFlexSpiIpCmdError_DataSizeNotEvenUnderParallelMode = 1,
    kFlexSpiIpCmdError_JumpOnCsInIpCmd = 2,
    kFlexSpiIpCmdError_UnknownOpCode = 3,
    kFlexSpiIpCmdError_SdrDummyInDdrSequence = 4,
    kFlexSpiIpCmdError_DDRDummyInSdrSequence = 5,
    kFlexSpiIpCmdError_InvalidAddress = 6,
    kFlexSpiIpCmdError_SequenceExecutionTimeout = 0x0E,
    kFlexSpiIpCmdError_FlashBoundaryAcrosss = 0x0F
} flexspi_ipcmd_error_t;

/* status code for flexspi */
enum _flexspi_status
{
    kStatus_FLEXSPI_SequenceExecutionTimeout =
        MAKE_STATUS(kStatusGroup_FLEXSPI, 0),                               //!< Status for Sequence Execution timeout
    kStatus_FLEXSPI_InvalidSequence = MAKE_STATUS(kStatusGroup_FLEXSPI, 1), //!< Status for Invalid Sequence
    kStatus_FLEXSPI_DeviceTimeout = MAKE_STATUS(kStatusGroup_FLEXSPI, 2),   //!< Status for Device timeout
};

//!@brief Misc feature bit definitions
enum
{
    kFlexSpiMiscOffset_DiffClkEnable            = 0, //!< Bit for Differential clock enable
    kFlexSpiMiscOffset_Ck2Enable                = 1, //!< Bit for CK2 enable
    kFlexSpiMiscOffset_ParallelEnable           = 2, //!< Bit for Parallel mode enable
    kFlexSpiMiscOffset_WordAddressableEnable    = 3, //!< Bit for Word Addressable enable
    kFlexSpiMiscOffset_SafeConfigFreqEnable     = 4, //!< Bit for Safe Configuration Frequency enable
    kFlexSpiMiscOffset_PadSettingOverrideEnable = 5, //!< Bit for Pad setting override enable
    kFlexSpiMiscOffset_DdrModeEnable            = 6, //!< Bit for DDR clock confiuration indication.
    kFlexSpiMiscOffset_UseValidTimeForAllFreq   = 7, //!< Bit for DLLCR settings under all modes
    kFlexSpiMiscOffset_SecondPinMux             = 8, //!< Bit for Second Pinmux group
    kFlexSpiMiscOffset_SecondDqsPinMux          = 9, //!< Bit for Second DQS Pinmux
};

//!@brief Flash Type Definition
enum
{
    kFlexSpiDeviceType_SerialNOR    = 1,    //!< Flash devices are Serial NOR
    kFlexSpiDeviceType_SerialNAND   = 2,    //!< Flash devices are Serial NAND
    kFlexSpiDeviceType_SerialRAM    = 3,    //!< Flash devices are Serial RAM/HyperFLASH
    kFlexSpiDeviceType_MCP_NOR_NAND = 0x12, //!< Flash device is MCP device, A1 is Serial NOR, A2 is Serial NAND
    kFlexSpiDeviceType_MCP_NOR_RAM  = 0x13, //!< Flash device is MCP device, A1 is Serial NOR, A2 is Serial RAMs
};

//!@brief Flash Pad Definitions
enum
{
    kSerialFlash_1Pad  = 1,
    kSerialFlash_2Pads = 2,
    kSerialFlash_4Pads = 4,
    kSerialFlash_8Pads = 8,
};

//!@brief FlexSPI LUT Sequence structure
typedef struct _lut_sequence
{
    uint8_t seqNum; //!< Sequence Number, valid number: 1-16
    uint8_t seqId;  //!< Sequence Index, valid number: 0-15
    uint16_t reserved;
} flexspi_lut_seq_t;

//!@brief Flash Configuration Command Type
enum
{
    kDeviceConfigCmdType_Generic,    //!< Generic command, for example: configure dummy cycles, drive strength, etc
    kDeviceConfigCmdType_QuadEnable, //!< Quad Enable command
    kDeviceConfigCmdType_Spi2Xpi,    //!< Switch from SPI to DPI/QPI/OPI mode
    kDeviceConfigCmdType_Xpi2Spi,    //!< Switch from DPI/QPI/OPI to SPI mode
    kDeviceConfigCmdType_Spi2NoCmd,  //!< Switch to 0-4-4/0-8-8 mode
    kDeviceConfigCmdType_Reset,      //!< Reset device command
};

typedef struct
{
    uint8_t time_100ps;  // Data valid time, in terms of 100ps
    uint8_t delay_cells; // Data valid time, in terms of delay cells
} flexspi_dll_time_t;

//!@brief FlexSPI Memory Configuration Block
typedef struct _FlexSPIConfig
{
    uint32_t tag;               //!< [0x000-0x003] Tag, fixed value 0x42464346UL
    uint32_t version;           //!< [0x004-0x007] Version,[31:24] -'V', [23:16] - Major, [15:8] - Minor, [7:0] - bugfix
    uint32_t reserved0;         //!< [0x008-0x00b] Reserved for future use
    uint8_t readSampleClkSrc;   //!< [0x00c-0x00c] Read Sample Clock Source, valid value: 0/1/3
    uint8_t csHoldTime;         //!< [0x00d-0x00d] CS hold time, default value: 3
    uint8_t csSetupTime;        //!< [0x00e-0x00e] CS setup time, default value: 3
    uint8_t columnAddressWidth; //!< [0x00f-0x00f] Column Address with, for HyperBus protocol, it is fixed to 3, For
    //! Serial NAND, need to refer to datasheet
    uint8_t deviceModeCfgEnable; //!< [0x010-0x010] Device Mode Configure enable flag, 1 - Enable, 0 - Disable
    uint8_t deviceModeType; //!< [0x011-0x011] Specify the configuration command type:Quad Enable, DPI/QPI/OPI switch,
    //! Generic configuration, etc.
    uint16_t waitTimeCfgCommands; //!< [0x012-0x013] Wait time for all configuration commands, unit: 100us, Used for
    //! DPI/QPI/OPI switch or reset command
    flexspi_lut_seq_t deviceModeSeq; //!< [0x014-0x017] Device mode sequence info, [7:0] - LUT sequence id, [15:8] - LUt
    //! sequence number, [31:16] Reserved
    uint32_t deviceModeArg;    //!< [0x018-0x01b] Argument/Parameter for device configuration
    uint8_t configCmdEnable;   //!< [0x01c-0x01c] Configure command Enable Flag, 1 - Enable, 0 - Disable
    uint8_t configModeType[3]; //!< [0x01d-0x01f] Configure Mode Type, similar as deviceModeTpe
    flexspi_lut_seq_t
        configCmdSeqs[3]; //!< [0x020-0x02b] Sequence info for Device Configuration command, similar as deviceModeSeq
    uint32_t reserved1;   //!< [0x02c-0x02f] Reserved for future use
    uint32_t configCmdArgs[3];     //!< [0x030-0x03b] Arguments/Parameters for device Configuration commands
    uint32_t reserved2;            //!< [0x03c-0x03f] Reserved for future use
    uint32_t controllerMiscOption; //!< [0x040-0x043] Controller Misc Options, see Misc feature bit definitions for more
    //! details
    uint8_t deviceType;    //!< [0x044-0x044] Device Type:  See Flash Type Definition for more details
    uint8_t sflashPadType; //!< [0x045-0x045] Serial Flash Pad Type: 1 - Single, 2 - Dual, 4 - Quad, 8 - Octal
    uint8_t serialClkFreq; //!< [0x046-0x046] Serial Flash Frequency, device specific definitions, See System Boot
    //! Chapter for more details
    uint8_t lutCustomSeqEnable; //!< [0x047-0x047] LUT customization Enable, it is required if the program/erase cannot
    //! be done using 1 LUT sequence, currently, only applicable to HyperFLASH
    uint32_t reserved3[2];               //!< [0x048-0x04f] Reserved for future use
    uint32_t sflashA1Size;               //!< [0x050-0x053] Size of Flash connected to A1
    uint32_t sflashA2Size;               //!< [0x054-0x057] Size of Flash connected to A2
    uint32_t sflashB1Size;               //!< [0x058-0x05b] Size of Flash connected to B1
    uint32_t sflashB2Size;               //!< [0x05c-0x05f] Size of Flash connected to B2
    uint32_t csPadSettingOverride;       //!< [0x060-0x063] CS pad setting override value
    uint32_t sclkPadSettingOverride;     //!< [0x064-0x067] SCK pad setting override value
    uint32_t dataPadSettingOverride;     //!< [0x068-0x06b] data pad setting override value
    uint32_t dqsPadSettingOverride;      //!< [0x06c-0x06f] DQS pad setting override value
    uint32_t timeoutInMs;                //!< [0x070-0x073] Timeout threshold for read status command
    uint32_t commandInterval;            //!< [0x074-0x077] CS deselect interval between two commands
    flexspi_dll_time_t dataValidTime[2]; //!< [0x078-0x07b] CLK edge to data valid time for PORT A and PORT B
    uint16_t busyOffset;                 //!< [0x07c-0x07d] Busy offset, valid value: 0-31
    uint16_t busyBitPolarity; //!< [0x07e-0x07f] Busy flag polarity, 0 - busy flag is 1 when flash device is busy, 1 -
    //! busy flag is 0 when flash device is busy
    uint32_t lookupTable[64];           //!< [0x080-0x17f] Lookup table holds Flash command sequences
    flexspi_lut_seq_t lutCustomSeq[12]; //!< [0x180-0x1af] Customizable LUT Sequences
    uint32_t reserved4[4];              //!< [0x1b0-0x1bf] Reserved for future use
} flexspi_mem_config_t;

typedef enum _FlexSPIOperationType
{
    kFlexSpiOperation_Command, //!< FlexSPI operation: Only command, both TX and
    //! RX buffer are ignored.
    kFlexSpiOperation_Config, //!< FlexSPI operation: Configure device mode, the
    //! TX FIFO size is fixed in LUT.
    kFlexSpiOperation_Write, //!< FlexSPI operation: Write,  only TX buffer is
    //! effective
    kFlexSpiOperation_Read, //!< FlexSPI operation: Read, only Rx Buffer is
    //! effective.
    kFlexSpiOperation_End = kFlexSpiOperation_Read,
} flexspi_operation_t;

//!@brief FlexSPI Transfer Context
typedef struct _FlexSpiXfer
{
    flexspi_operation_t operation; //!< FlexSPI operation
    uint32_t baseAddress;          //!< FlexSPI operation base address
    uint32_t seqId;                //!< Sequence Id
    uint32_t seqNum;               //!< Sequence Number
    bool isParallelModeEnable;     //!< Is a parallel transfer
    uint32_t *txBuffer;            //!< Tx buffer
    uint32_t txSize;               //!< Tx size in bytes
    uint32_t *rxBuffer;            //!< Rx buffer
    uint32_t rxSize;               //!< Rx size in bytes
} flexspi_xfer_t;

//!@brief FlexSPI Clock Type
typedef enum
{
    kFlexSpiClock_CoreClock,       //!< ARM Core Clock
    kFlexSpiClock_AhbClock,        //!< AHB clock
    kFlexSpiClock_SerialRootClock, //!< Serial Root Clock
    kFlexSpiClock_IpgClock,        //!< IPG clock
} flexspi_clock_type_t;

//!@brief Generate bit mask
#define FLEXSPI_BITMASK(bit_offset) (1u << (bit_offset))

#ifndef FLEXSPI_ENABLE_OCTAL_FLASH_SUPPORT
#define FLEXSPI_ENABLE_OCTAL_FLASH_SUPPORT (1)
#endif

#ifndef FLEXSPI_ENABLE_NO_CMD_MODE_SUPPORT
#define FLEXSPI_ENABLE_NO_CMD_MODE_SUPPORT (1)
#endif

#endif
