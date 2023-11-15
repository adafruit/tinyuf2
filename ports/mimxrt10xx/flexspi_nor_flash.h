/*
 * Copyright 2014-2015 Freescale Semiconductor, Inc.
 * Copyright 2016-2020 NXP
 * All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 */

#ifndef __FLEXSPI_NOR_FLASH_H__
#define __FLEXSPI_NOR_FLASH_H__

#include "fsl_common.h"
#include "bl_flexspi.h"

// Seems to be not used !
//#define NOR_CMD_INDEX_READ          CMD_INDEX_READ        //!< 0
//#define NOR_CMD_INDEX_READSTATUS    CMD_INDEX_READSTATUS  //!< 1
//#define NOR_CMD_INDEX_WRITEENABLE   CMD_INDEX_WRITEENABLE //!< 2
//#define NOR_CMD_INDEX_ERASESECTOR   3                     //!< 3
//#define NOR_CMD_INDEX_PAGEPROGRAM   CMD_INDEX_WRITE       //!< 4
//#define NOR_CMD_INDEX_CHIPERASE     5                     //!< 5
//#define NOR_CMD_INDEX_DUMMY         6                     //!< 6
//#define NOR_CMD_INDEX_ERASEBLOCK    7                     //!< 7

// Command index in flexspi_nor_config_t's look-up table
#define NOR_CMD_LUT_SEQ_IDX_READ              CMD_LUT_SEQ_IDX_READ        //!< 0  READ LUT sequence id in lookupTable stored in config block
#define NOR_CMD_LUT_SEQ_IDX_READSTATUS        CMD_LUT_SEQ_IDX_READSTATUS  //!< 1  Read Status LUT sequence id in lookupTable stored in config block
#define NOR_CMD_LUT_SEQ_IDX_READSTATUS_XPI    2                           //!< 2  Read status DPI/QPI/OPI sequence id in lookupTable stored in config block
#define NOR_CMD_LUT_SEQ_IDX_WRITEENABLE       CMD_LUT_SEQ_IDX_WRITEENABLE //!< 3  Write Enable sequence id in lookupTable stored in config block
#define NOR_CMD_LUT_SEQ_IDX_WRITEENABLE_XPI   4                           //!< 4  Write Enable DPI/QPI/OPI sequence id in lookupTable stored in config block
#define NOR_CMD_LUT_SEQ_IDX_ERASESECTOR       5                           //!< 5  Erase Sector sequence id in lookupTable stored in config block
#define NOR_CMD_LUT_SEQ_IDX_ERASEBLOCK        8                           //!< 8 Erase Block sequence id in lookupTable stored in config block
#define NOR_CMD_LUT_SEQ_IDX_PAGEPROGRAM       CMD_LUT_SEQ_IDX_WRITE       //!< 9  Program sequence id in lookupTable stored in config block
#define NOR_CMD_LUT_SEQ_IDX_CHIPERASE         11                          //!< 11 Chip Erase sequence in lookupTable id stored in config block
#define NOR_CMD_LUT_SEQ_IDX_READ_SFDP         13                          //!< 13 Read SFDP sequence in lookupTable id stored in config block
#define NOR_CMD_LUT_SEQ_IDX_RESTORE_NOCMD     14                          //!< 14 Restore 0-4-4/0-8-8 mode sequence id in lookupTable stored in config block
#define NOR_CMD_LUT_SEQ_IDX_EXIT_NOCMD        15                          //!< 15 Exit 0-4-4/0-8-8 mode sequence id in lookupTable stored in config blobk

/* FlexSPI NOR status */
enum _flexspi_nor_status
{
    kStatusGroup_FLEXSPINOR                     = 201,                                      //!< FlexSPINOR status group number.
    kStatus_FLEXSPINOR_ProgramFail              = MAKE_STATUS(kStatusGroup_FLEXSPINOR, 0),  //!< Status for Page programming failure
    kStatus_FLEXSPINOR_EraseSectorFail          = MAKE_STATUS(kStatusGroup_FLEXSPINOR, 1),  //!< Status for Sector Erase failure
    kStatus_FLEXSPINOR_EraseAllFail             = MAKE_STATUS(kStatusGroup_FLEXSPINOR, 2),  //!< Status for Chip Erase failure
    kStatus_FLEXSPINOR_WaitTimeout              = MAKE_STATUS(kStatusGroup_FLEXSPINOR, 3),  //!< Status for timeout
    kStatus_FlexSPINOR_NotSupported             = MAKE_STATUS(kStatusGroup_FLEXSPINOR, 4),  // Status for PageSize overflow
    kStatus_FlexSPINOR_WriteAlignmentError      = MAKE_STATUS(kStatusGroup_FLEXSPINOR, 5),  //!< Status for Alignment error
    kStatus_FlexSPINOR_CommandFailure           = MAKE_STATUS(kStatusGroup_FLEXSPINOR, 6),  //!< Status for Erase/Program Verify Error
    kStatus_FlexSPINOR_SFDP_NotFound            = MAKE_STATUS(kStatusGroup_FLEXSPINOR, 7),  //!< Status for SFDP read failure
    kStatus_FLEXSPINOR_Unsupported_SFDP_Version = MAKE_STATUS(kStatusGroup_FLEXSPINOR, 8),  //!< Status for Unrecognized SFDP version
    kStatus_FLEXSPINOR_Flash_NotFound           = MAKE_STATUS(kStatusGroup_FLEXSPINOR, 9),  //!< Status for Flash detection failure
    kStatus_FLEXSPINOR_DTRRead_DummyProbeFailed = MAKE_STATUS(kStatusGroup_FLEXSPINOR, 10), //!< Status for DDR Read dummy probe failure
};

enum
{
    kSerialNorCfgOption_Tag                         = 0x0c,
    kSerialNorCfgOption_DeviceType_ReadSFDP_SDR     = 0,
    kSerialNorCfgOption_DeviceType_ReadSFDP_DDR     = 1,
    kSerialNorCfgOption_DeviceType_HyperFLASH1V8    = 2,
    kSerialNorCfgOption_DeviceType_HyperFLASH3V0    = 3,
    kSerialNorCfgOption_DeviceType_MacronixOctalDDR = 4,
    kSerialNorCfgOption_DeviceType_MacronixOctalSDR = 5,
    kSerialNorCfgOption_DeviceType_MicronOctalDDR   = 6,
    kSerialNorCfgOption_DeviceType_MicronOctalSDR   = 7,
    kSerialNorCfgOption_DeviceType_AdestoOctalDDR   = 8,
    kSerialNorCfgOption_DeviceType_AdestoOctalSDR   = 9,
};

enum
{
    kSerialNorQuadMode_NotConfig            = 0,
    kSerialNorQuadMode_StatusReg1_Bit6      = 1,
    kSerialNorQuadMode_StatusReg2_Bit1      = 2,
    kSerialNorQuadMode_StatusReg2_Bit7      = 3,
    kSerialNorQuadMode_StatusReg2_Bit1_0x31 = 4,
};

enum
{
    kSerialNorEnhanceMode_Disabled         = 0,
    kSerialNorEnhanceMode_0_4_4_Mode       = 1,
    kSerialNorEnhanceMode_0_8_8_Mode       = 2,
    kSerialNorEnhanceMode_DataOrderSwapped = 3,
    kSerialNorEnhanceMode_2ndPinMux        = 4,
    kSerialNorEnhanceMode_InternalLoopback = 5,
};

enum
{
    kSerialNorConnection_SinglePortA,
    kSerialNorConnection_Parallel,
    kSerialNorConnection_SinglePortB,
    kSerialNorConnection_BothPorts
};

/*
 * Serial NOR Configuration Option
 */
typedef struct _serial_nor_config_option
{
    union
    {
        struct
        {
            uint32_t max_freq : 4;          //!< Maximum supported Frequency
            uint32_t misc_mode : 4;         //!< miscellaneous mode
            uint32_t quad_mode_setting : 4; //!< Quad mode setting
            uint32_t cmd_pads : 4;          //!< Command pads
            uint32_t query_pads : 4;        //!< SFDP read pads
            uint32_t device_type : 4;       //!< Device type
            uint32_t option_size : 4;       //!< Option size, in terms of uint32_t, size = (option_size + 1) * 4
            uint32_t tag : 4;               //!< Tag, must be 0x0E
        } B;
        uint32_t U;
    } option0;

    union
    {
        struct
        {
            uint32_t dummy_cycles : 8;     //!< Dummy cycles before read
            uint32_t status_override : 8;  //!< Override status register value during device mode configuration
            uint32_t pinmux_group : 4;     //!< The pinmux group selection
            uint32_t dqs_pinmux_group : 4; //!< The DQS Pinmux Group Selection
            uint32_t drive_strength : 4;   //!< The Drive Strength of FlexSPI Pads
            uint32_t flash_connection : 4; //!< Flash connection option: 0 - Single Flash connected to port A, 1 -
            //! Parallel mode, 2 - Single Flash connected to Port B
        } B;
        uint32_t U;
    } option1;

} serial_nor_config_option_t;

typedef union
{
    struct
    {
        uint8_t por_mode;
        uint8_t current_mode;
        uint8_t exit_no_cmd_sequence;
        uint8_t restore_sequence;
    } B;
    uint32_t U;
} flash_run_context_t;

enum
{
    kRestoreSequence_None = 0,
    kRestoreSequence_HW_Reset = 1,
    kRestoreSequence_4QPI_FF = 2,
    kRestoreSequence_5QPI_FF = 3,
    kRestoreSequence_8QPI_FF = 4,
    kRestoreSequence_Send_F0 = 5,
    kRestoreSequence_Send_66_99 = 6,
    kRestoreSequence_Send_6699_9966 = 7,
    kRestoreSequence_Send_06_FF, // Adesto EcoXIP
};

enum
{
    kFlashInstMode_ExtendedSpi = 0x00,
    kFlashInstMode_0_4_4_SDR = 0x01,
    kFlashInstMode_0_4_4_DDR = 0x02,
    kFlashInstMode_QPI_SDR = 0x41,
    kFlashInstMode_QPI_DDR = 0x42,
    kFlashInstMode_OPI_SDR = 0x81,
    kFlashInstMode_OPI_DDR = 0x82,
};

/*
 *  Serial NOR configuration block
 */
typedef struct _flexspi_nor_config
{
    flexspi_mem_config_t memConfig; //!< Common memory configuration info via FlexSPI
    uint32_t pageSize;              //!< Page size of Serial NOR
    uint32_t sectorSize;            //!< Sector size of Serial NOR
    uint8_t ipcmdSerialClkFreq;     //!< Clock frequency for IP command
    uint8_t isUniformBlockSize;     //!< Sector/Block size is the same
    uint8_t isDataOrderSwapped;     //!< Data order (D0, D1, D2, D3) is swapped (D1,D0, D3, D2)
    uint8_t reserved0[1];           //!< Reserved for future use
    uint8_t serialNorType;          //!< Serial NOR Flash type: 0/1/2/3
    uint8_t needExitNoCmdMode;      //!< Need to exit NoCmd mode before other IP command
    uint8_t halfClkForNonReadCmd;   //!< Half the Serial Clock for non-read command: true/false
    uint8_t needRestoreNoCmdMode;   //!< Need to Restore NoCmd mode after IP command execution
    uint32_t blockSize;             //!< Block size
    uint32_t reserve2[11];          //!< Reserved for future use
} flexspi_nor_config_t;

#endif // __FLEXSPI_NOR_FLASH_H__
