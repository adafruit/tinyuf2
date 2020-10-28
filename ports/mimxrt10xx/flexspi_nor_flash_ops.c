/*
 * Copyright (c) 2016, Freescale Semiconductor, Inc.
 * Copyright 2016-2019 NXP
 * All rights reserved.
 *
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#include "fsl_flexspi.h"
#include "boards.h"

#include <stdio.h>

/*******************************************************************************
 * Definitions
 ******************************************************************************/
#define FLEXSPI_LUT_KEY_VAL (0x5AF05AF0ul)

#define EXAMPLE_FLEXSPI FLEXSPI
#define FLASH_SIZE 0x2000 /* 64Mb/KByte */
#define EXAMPLE_FLEXSPI_AMBA_BASE FlexSPI_AMBA_BASE
#define FLASH_PAGE_SIZE 256
#define EXAMPLE_SECTOR 0
#define SECTOR_SIZE 0x1000 /* 4K */
#define EXAMPLE_FLEXSPI_CLOCK kCLOCK_FlexSpi

#define NOR_CMD_LUT_SEQ_IDX_READ_NORMAL 7
#define NOR_CMD_LUT_SEQ_IDX_READ_FAST 13
#define NOR_CMD_LUT_SEQ_IDX_READ_FAST_QUAD 0
#define NOR_CMD_LUT_SEQ_IDX_READSTATUS 1
#define NOR_CMD_LUT_SEQ_IDX_WRITEENABLE 2
#define NOR_CMD_LUT_SEQ_IDX_ERASESECTOR 3
#define NOR_CMD_LUT_SEQ_IDX_PAGEPROGRAM_SINGLE 6
#define NOR_CMD_LUT_SEQ_IDX_PAGEPROGRAM_QUAD 4
#define NOR_CMD_LUT_SEQ_IDX_READID 8
#define NOR_CMD_LUT_SEQ_IDX_WRITESTATUSREG 9
#define NOR_CMD_LUT_SEQ_IDX_ENTERQPI 10
#define NOR_CMD_LUT_SEQ_IDX_EXITQPI 11
#define NOR_CMD_LUT_SEQ_IDX_READSTATUSREG 12
#define NOR_CMD_LUT_SEQ_IDX_ERASECHIP 5

#define CUSTOM_LUT_LENGTH 60
#define FLASH_QUAD_ENABLE 0x40 // TODO depend on flash device
#define FLASH_BUSY_STATUS_POL 1
#define FLASH_BUSY_STATUS_OFFSET 0

/*******************************************************************************
 * Prototypes
 ******************************************************************************/

static inline void flexspi_clock_init(void)
{
#if defined(XIP_EXTERNAL_FLASH) && (XIP_EXTERNAL_FLASH == 1)
    /* Switch to PLL2 for XIP to avoid hardfault during re-initialize clock. */
    CLOCK_InitSysPfd(kCLOCK_Pfd2, 24);    /* Set PLL2 PFD2 clock 396MHZ. */
    CLOCK_SetMux(kCLOCK_FlexspiMux, 0x2); /* Choose PLL2 PFD2 clock as flexspi source clock. */
    CLOCK_SetDiv(kCLOCK_FlexspiDiv, 2);   /* flexspi clock 133M. */
#else
    const clock_usb_pll_config_t g_ccmConfigUsbPll = {.loopDivider = 0U};

    CLOCK_InitUsb1Pll(&g_ccmConfigUsbPll);
    CLOCK_InitUsb1Pfd(kCLOCK_Pfd0, 24);   /* Set PLL3 PFD0 clock 360MHZ. */
    CLOCK_SetMux(kCLOCK_FlexspiMux, 0x3); /* Choose PLL3 PFD0 clock as flexspi source clock. */
    CLOCK_SetDiv(kCLOCK_FlexspiDiv, 2);   /* flexspi clock 120M. */
#endif
}

/*******************************************************************************
 * Variables
 *****************************************************************************/
uint32_t g_customLUT[CUSTOM_LUT_LENGTH] =
{
  /* Normal read mode -SDR */
  [4 * NOR_CMD_LUT_SEQ_IDX_READ_NORMAL] =
      FLEXSPI_LUT_SEQ(kFLEXSPI_Command_SDR, kFLEXSPI_1PAD, 0x03, kFLEXSPI_Command_RADDR_SDR, kFLEXSPI_1PAD, 0x18),
  [4 * NOR_CMD_LUT_SEQ_IDX_READ_NORMAL + 1] =
      FLEXSPI_LUT_SEQ(kFLEXSPI_Command_READ_SDR, kFLEXSPI_1PAD, 0x04, kFLEXSPI_Command_STOP, kFLEXSPI_1PAD, 0),

  /* Fast read mode - SDR */
  [4 * NOR_CMD_LUT_SEQ_IDX_READ_FAST] =
      FLEXSPI_LUT_SEQ(kFLEXSPI_Command_SDR, kFLEXSPI_1PAD, 0x0B, kFLEXSPI_Command_RADDR_SDR, kFLEXSPI_1PAD, 0x18),
  [4 * NOR_CMD_LUT_SEQ_IDX_READ_FAST + 1] = FLEXSPI_LUT_SEQ(
      kFLEXSPI_Command_DUMMY_SDR, kFLEXSPI_1PAD, 0x08, kFLEXSPI_Command_READ_SDR, kFLEXSPI_1PAD, 0x04),

  /* Fast read quad mode - SDR */
  [4 * NOR_CMD_LUT_SEQ_IDX_READ_FAST_QUAD] =
      FLEXSPI_LUT_SEQ(kFLEXSPI_Command_SDR, kFLEXSPI_1PAD, 0xEB, kFLEXSPI_Command_RADDR_SDR, kFLEXSPI_4PAD, 0x18),
  [4 * NOR_CMD_LUT_SEQ_IDX_READ_FAST_QUAD + 1] = FLEXSPI_LUT_SEQ(
      kFLEXSPI_Command_DUMMY_SDR, kFLEXSPI_4PAD, 0x06, kFLEXSPI_Command_READ_SDR, kFLEXSPI_4PAD, 0x04),

  /* Read extend parameters */
  [4 * NOR_CMD_LUT_SEQ_IDX_READSTATUS] =
      FLEXSPI_LUT_SEQ(kFLEXSPI_Command_SDR, kFLEXSPI_1PAD, 0x81, kFLEXSPI_Command_READ_SDR, kFLEXSPI_1PAD, 0x04),

  /* Write Enable */
  [4 * NOR_CMD_LUT_SEQ_IDX_WRITEENABLE] =
      FLEXSPI_LUT_SEQ(kFLEXSPI_Command_SDR, kFLEXSPI_1PAD, 0x06, kFLEXSPI_Command_STOP, kFLEXSPI_1PAD, 0),

  /* Erase Sector  */
  [4 * NOR_CMD_LUT_SEQ_IDX_ERASESECTOR] =
      FLEXSPI_LUT_SEQ(kFLEXSPI_Command_SDR, kFLEXSPI_1PAD, 0x20, kFLEXSPI_Command_RADDR_SDR, kFLEXSPI_1PAD, 0x18),

  /* Page Program - single mode */
  [4 * NOR_CMD_LUT_SEQ_IDX_PAGEPROGRAM_SINGLE] =
      FLEXSPI_LUT_SEQ(kFLEXSPI_Command_SDR, kFLEXSPI_1PAD, 0x02, kFLEXSPI_Command_RADDR_SDR, kFLEXSPI_1PAD, 0x18),
  [4 * NOR_CMD_LUT_SEQ_IDX_PAGEPROGRAM_SINGLE + 1] =
      FLEXSPI_LUT_SEQ(kFLEXSPI_Command_WRITE_SDR, kFLEXSPI_1PAD, 0x04, kFLEXSPI_Command_STOP, kFLEXSPI_1PAD, 0),

  /* Page Program - quad mode */
  [4 * NOR_CMD_LUT_SEQ_IDX_PAGEPROGRAM_QUAD] =
      FLEXSPI_LUT_SEQ(kFLEXSPI_Command_SDR, kFLEXSPI_1PAD, 0x32, kFLEXSPI_Command_RADDR_SDR, kFLEXSPI_1PAD, 0x18),
  [4 * NOR_CMD_LUT_SEQ_IDX_PAGEPROGRAM_QUAD + 1] =
      FLEXSPI_LUT_SEQ(kFLEXSPI_Command_WRITE_SDR, kFLEXSPI_4PAD, 0x04, kFLEXSPI_Command_STOP, kFLEXSPI_1PAD, 0),

  /* Read ID */
  [4 * NOR_CMD_LUT_SEQ_IDX_READID] =
      FLEXSPI_LUT_SEQ(kFLEXSPI_Command_SDR, kFLEXSPI_1PAD, 0xAB, kFLEXSPI_Command_DUMMY_SDR, kFLEXSPI_1PAD, 0x18),
  [4 * NOR_CMD_LUT_SEQ_IDX_READID + 1] =
      FLEXSPI_LUT_SEQ(kFLEXSPI_Command_READ_SDR, kFLEXSPI_1PAD, 0x04, kFLEXSPI_Command_STOP, kFLEXSPI_1PAD, 0),

  /* Enable Quad mode */
  [4 * NOR_CMD_LUT_SEQ_IDX_WRITESTATUSREG] =
      FLEXSPI_LUT_SEQ(kFLEXSPI_Command_SDR, kFLEXSPI_1PAD, 0x01, kFLEXSPI_Command_WRITE_SDR, kFLEXSPI_1PAD, 0x04),

  /* Enter QPI mode */
  [4 * NOR_CMD_LUT_SEQ_IDX_ENTERQPI] =
      FLEXSPI_LUT_SEQ(kFLEXSPI_Command_SDR, kFLEXSPI_1PAD, 0x35, kFLEXSPI_Command_STOP, kFLEXSPI_1PAD, 0),

  /* Exit QPI mode */
  [4 * NOR_CMD_LUT_SEQ_IDX_EXITQPI] =
      FLEXSPI_LUT_SEQ(kFLEXSPI_Command_SDR, kFLEXSPI_4PAD, 0xF5, kFLEXSPI_Command_STOP, kFLEXSPI_1PAD, 0),

  /* Read status register */
  [4 * NOR_CMD_LUT_SEQ_IDX_READSTATUSREG] =
      FLEXSPI_LUT_SEQ(kFLEXSPI_Command_SDR, kFLEXSPI_1PAD, 0x05, kFLEXSPI_Command_READ_SDR, kFLEXSPI_1PAD, 0x04),

  /* Erase whole chip */
  [4 * NOR_CMD_LUT_SEQ_IDX_ERASECHIP] =
      FLEXSPI_LUT_SEQ(kFLEXSPI_Command_SDR, kFLEXSPI_1PAD, 0xC7, kFLEXSPI_Command_STOP, kFLEXSPI_1PAD, 0),
};

/*******************************************************************************
 * Code
 ******************************************************************************/

AT_QUICKACCESS_SECTION_CODE(void AHBPrefetchEnable(FLEXSPI_Type *base))
{
  base->AHBCR |= 0x20;
}
AT_QUICKACCESS_SECTION_CODE(void AHBPrefetchDisable(FLEXSPI_Type *base))
{
  base->AHBCR &= ~0x20;
}
AT_QUICKACCESS_SECTION_CODE(void FLEXSPI_SoftwareResetRamfunc(FLEXSPI_Type *base))
{
    base->MCR0 |= FLEXSPI_MCR0_SWRESET_MASK;
    while (base->MCR0 & FLEXSPI_MCR0_SWRESET_MASK)
    {
    }
}
AT_QUICKACCESS_SECTION_CODE(status_t FLEXSPI_CheckAndClearErrorRamfunc(FLEXSPI_Type *base, uint32_t status))
{
    status_t result = kStatus_Success;

    /* Check for error. */
    status &= kFLEXSPI_SequenceExecutionTimeoutFlag | kFLEXSPI_IpCommandSequenceErrorFlag |
                  kFLEXSPI_IpCommandGrantTimeoutFlag;
    if (status)
    {
        /* Select the correct error code.. */
        if (status & kFLEXSPI_SequenceExecutionTimeoutFlag)
        {
            result = kStatus_FLEXSPI_SequenceExecutionTimeout;
        }
        else if (status & kFLEXSPI_IpCommandSequenceErrorFlag)
        {
            result = kStatus_FLEXSPI_IpCommandSequenceError;
        }
        else if (status & kFLEXSPI_IpCommandGrantTimeoutFlag)
        {
            result = kStatus_FLEXSPI_IpCommandGrantTimeout;
        }
        else
        {
            assert(false);
        }

        /* Clear the flags. */
        base->INTR = status;
        //FLEXSPI_ClearInterruptStatusFlags(base, status);

        /* Reset fifos. These flags clear automatically. */
        base->IPTXFCR |= FLEXSPI_IPTXFCR_CLRIPTXF_MASK;
        base->IPRXFCR |= FLEXSPI_IPRXFCR_CLRIPRXF_MASK;
    }

    return result;
}
AT_QUICKACCESS_SECTION_CODE(status_t FLEXSPI_WriteBlockingRamfunc(FLEXSPI_Type *base, uint32_t *buffer, size_t size))
{
    uint8_t txWatermark = ((base->IPTXFCR & FLEXSPI_IPTXFCR_TXWMRK_MASK) >> FLEXSPI_IPTXFCR_TXWMRK_SHIFT) + 1;
    uint32_t status;
    status_t result = kStatus_Success;
    uint32_t i = 0;

    /* Send data buffer */
    while (size)
    {
        /* Wait until there is room in the fifo. This also checks for errors. */
        while (!((status = base->INTR) & kFLEXSPI_IpTxFifoWatermarkEmpltyFlag))
        {
        }

        result = FLEXSPI_CheckAndClearErrorRamfunc(base, status);

        if (result)
        {
            return result;
        }

        /* Write watermark level data into tx fifo . */
        if (size >= 8 * txWatermark)
        {
            for (i = 0; i < 2 * txWatermark; i++)
            {
                base->TFDR[i] = *buffer++;
            }

            size = size - 8 * txWatermark;
        }
        else
        {
            for (i = 0; i < (size / 4 + 1); i++)
            {
                base->TFDR[i] = *buffer++;
            }
            size = 0;
        }

        /* Push a watermark level datas into IP TX FIFO. */
        base->INTR |= kFLEXSPI_IpTxFifoWatermarkEmpltyFlag;
    }

    return result;
}

/*!
 * brief Receives a buffer of data bytes using a blocking method.
 * note This function blocks via polling until all bytes have been sent.
 * param base FLEXSPI peripheral base address
 * param buffer The data bytes to send
 * param size The number of data bytes to receive
 * retval kStatus_Success read success without error
 * retval kStatus_FLEXSPI_SequenceExecutionTimeout sequence execution timeout
 * retval kStatus_FLEXSPI_IpCommandSequenceError IP command sequencen error detected
 * retval kStatus_FLEXSPI_IpCommandGrantTimeout IP command grant timeout detected
 */
AT_QUICKACCESS_SECTION_CODE(status_t FLEXSPI_ReadBlockingRamfunc(FLEXSPI_Type *base, uint32_t *buffer, size_t size))
{
    uint8_t rxWatermark = ((base->IPRXFCR & FLEXSPI_IPRXFCR_RXWMRK_MASK) >> FLEXSPI_IPRXFCR_RXWMRK_SHIFT) + 1;
    uint32_t status;
    status_t result = kStatus_Success;
    uint32_t i = 0;

    /* Send data buffer */
    while (size)
    {
        if (size >= 8 * rxWatermark)
        {
            /* Wait until there is room in the fifo. This also checks for errors. */
            while (!((status = base->INTR) & kFLEXSPI_IpRxFifoWatermarkAvailableFlag))
            {
                result = FLEXSPI_CheckAndClearErrorRamfunc(base, status);

                if (result)
                {
                    return result;
                }
            }
        }
        else
        {
            /* Wait fill level. This also checks for errors. */
            while (size > ((((base->IPRXFSTS) & FLEXSPI_IPRXFSTS_FILL_MASK) >> FLEXSPI_IPRXFSTS_FILL_SHIFT) * 8U))
            {
                result = FLEXSPI_CheckAndClearErrorRamfunc(base, base->INTR);

                if (result)
                {
                    return result;
                }
            }
        }

        result = FLEXSPI_CheckAndClearErrorRamfunc(base, base->INTR);

        if (result)
        {
            return result;
        }

        /* Read watermark level data from rx fifo . */
        if (size >= 8 * rxWatermark)
        {
            for (i = 0; i < 2 * rxWatermark; i++)
            {
                *buffer++ = base->RFDR[i];
            }

            size = size - 8 * rxWatermark;
        }
        else
        {
            for (i = 0; i < (size / 4 + 1); i++)
            {
                *buffer++ = base->RFDR[i];
            }
            size = 0;
        }

        /* Pop out a watermark level datas from IP RX FIFO. */
        base->INTR |= kFLEXSPI_IpRxFifoWatermarkAvailableFlag;
    }

    return result;
}
AT_QUICKACCESS_SECTION_CODE(status_t FLEXSPI_TransferBlockingRamfunc(FLEXSPI_Type *base, flexspi_transfer_t *xfer))
{
    uint32_t configValue = 0;
    status_t result = kStatus_Success;

    /* Clear sequence pointer before sending data to external devices. */
    base->FLSHCR2[xfer->port] |= FLEXSPI_FLSHCR2_CLRINSTRPTR_MASK;

    /* Clear former pending status before start this tranfer. */
    base->INTR |= FLEXSPI_INTR_AHBCMDERR_MASK | FLEXSPI_INTR_IPCMDERR_MASK | FLEXSPI_INTR_AHBCMDGE_MASK |
                  FLEXSPI_INTR_IPCMDGE_MASK;

    /* Configure base addresss. */
    base->IPCR0 = xfer->deviceAddress;

    /* Reset fifos. */
    base->IPTXFCR |= FLEXSPI_IPTXFCR_CLRIPTXF_MASK;
    base->IPRXFCR |= FLEXSPI_IPRXFCR_CLRIPRXF_MASK;

    /* Configure data size. */
    if ((xfer->cmdType == kFLEXSPI_Read) || (xfer->cmdType == kFLEXSPI_Write) || (xfer->cmdType == kFLEXSPI_Config))
    {
        configValue = FLEXSPI_IPCR1_IDATSZ(xfer->dataSize);
    }

    /* Configure sequence ID. */
    configValue |= FLEXSPI_IPCR1_ISEQID(xfer->seqIndex) | FLEXSPI_IPCR1_ISEQNUM(xfer->SeqNumber - 1);
    base->IPCR1 = configValue;

    /* Start Transfer. */
    base->IPCMD |= FLEXSPI_IPCMD_TRG_MASK;

    if ((xfer->cmdType == kFLEXSPI_Write) || (xfer->cmdType == kFLEXSPI_Config))
    {
        result = FLEXSPI_WriteBlockingRamfunc(base, xfer->data, xfer->dataSize);
    }
    else if (xfer->cmdType == kFLEXSPI_Read)
    {
        result = FLEXSPI_ReadBlockingRamfunc(base, xfer->data, xfer->dataSize);
    }
    else
    {
    }

    /* Wait for bus idle. */
    while (!((base->STS0 & FLEXSPI_STS0_ARBIDLE_MASK) && (base->STS0 & FLEXSPI_STS0_SEQIDLE_MASK)))
    {
    }

    if (xfer->cmdType == kFLEXSPI_Command)
    {
        result = FLEXSPI_CheckAndClearErrorRamfunc(base, base->INTR);
    }

    return result;
}

AT_QUICKACCESS_SECTION_CODE(status_t flexspi_nor_write_enable(FLEXSPI_Type *base, uint32_t baseAddr))
{
    flexspi_transfer_t flashXfer;
    status_t status;

    /* Write enable */
    flashXfer.deviceAddress = baseAddr;
    flashXfer.port = kFLEXSPI_PortA1;
    flashXfer.cmdType = kFLEXSPI_Command;
    flashXfer.SeqNumber = 1;
    flashXfer.seqIndex = NOR_CMD_LUT_SEQ_IDX_WRITEENABLE;

    status = FLEXSPI_TransferBlockingRamfunc(base, &flashXfer);

    return status;
}

AT_QUICKACCESS_SECTION_CODE(void FLEXSPI_UpdateLUTRamfunc(FLEXSPI_Type *base, uint32_t index, const uint32_t *cmd, uint32_t count))
{
    assert(index < 64U);
    //this is to abort on-going prefetching
    AHBPrefetchDisable(EXAMPLE_FLEXSPI);

    uint8_t i = 0;
    volatile uint32_t *lutBase;

    /* Wait for bus idle before change flash configuration. */
    while (!((base->STS0 & FLEXSPI_STS0_ARBIDLE_MASK) && (base->STS0 & FLEXSPI_STS0_SEQIDLE_MASK)))
    {
    }

    /* Unlock LUT for update. */
    base->LUTKEY = FLEXSPI_LUT_KEY_VAL;
    base->LUTCR = 0x02;

    lutBase = &base->LUT[index];
    for (i = 0; i < count; i++)
    {
        *lutBase++ = *cmd++;
    }

    /* Lock LUT. */
    base->LUTKEY = FLEXSPI_LUT_KEY_VAL;
    base->LUTCR = 0x01;

    AHBPrefetchEnable(EXAMPLE_FLEXSPI);
}

void flexspi_nor_flash_init(FLEXSPI_Type *base)
{
  FLEXSPI_UpdateLUTRamfunc(base, 4, &g_customLUT[4], CUSTOM_LUT_LENGTH-4);
}

AT_QUICKACCESS_SECTION_CODE(status_t flexspi_nor_wait_bus_busy(FLEXSPI_Type *base))
{
    /* Wait status ready. */
    bool isBusy;
    uint32_t readValue;
    status_t status;
    flexspi_transfer_t flashXfer;

    flashXfer.deviceAddress = 0;
    flashXfer.port = kFLEXSPI_PortA1;
    flashXfer.cmdType = kFLEXSPI_Read;
    flashXfer.SeqNumber = 1;
    flashXfer.seqIndex = NOR_CMD_LUT_SEQ_IDX_READSTATUSREG;
    flashXfer.data = &readValue;
    flashXfer.dataSize = 1;

    do
    {
        status = FLEXSPI_TransferBlockingRamfunc(base, &flashXfer);

        if (status != kStatus_Success)
        {
            return status;
        }
        if (FLASH_BUSY_STATUS_POL)
        {
            if (readValue & (1U << FLASH_BUSY_STATUS_OFFSET))
            {
                isBusy = true;
            }
            else
            {
                isBusy = false;
            }
        }
        else
        {
            if (readValue & (1U << FLASH_BUSY_STATUS_OFFSET))
            {
                isBusy = false;
            }
            else
            {
                isBusy = true;
            }
        }

    } while (isBusy);

    return status;
}

status_t flexspi_nor_enable_quad_mode(FLEXSPI_Type *base)
{
    flexspi_transfer_t flashXfer;
    status_t status;
    uint32_t writeValue = FLASH_QUAD_ENABLE;

    /* Write enable */
    status = flexspi_nor_write_enable(base, 0);

    if (status != kStatus_Success)
    {
        return status;
    }

    /* Enable quad mode. */
    flashXfer.deviceAddress = 0;
    flashXfer.port = kFLEXSPI_PortA1;
    flashXfer.cmdType = kFLEXSPI_Write;
    flashXfer.SeqNumber = 1;
    flashXfer.seqIndex = NOR_CMD_LUT_SEQ_IDX_WRITESTATUSREG;
    flashXfer.data = &writeValue;
    flashXfer.dataSize = 1;

    status = FLEXSPI_TransferBlocking(base, &flashXfer);
    if (status != kStatus_Success)
    {
        return status;
    }

    status = flexspi_nor_wait_bus_busy(base);

    return status;
}

AT_QUICKACCESS_SECTION_CODE(status_t flexspi_nor_flash_erase_sector(FLEXSPI_Type *base, uint32_t address))
{
    status_t status;
    flexspi_transfer_t flashXfer;

    AHBPrefetchDisable(FLEXSPI);

    /* Write enable */
    flashXfer.deviceAddress = address;
    flashXfer.port = kFLEXSPI_PortA1;
    flashXfer.cmdType = kFLEXSPI_Command;
    flashXfer.SeqNumber = 1;
    flashXfer.seqIndex = NOR_CMD_LUT_SEQ_IDX_WRITEENABLE;

    status = FLEXSPI_TransferBlockingRamfunc(base, &flashXfer);

    if (status != kStatus_Success)
    {
        FLEXSPI_SoftwareResetRamfunc(FLEXSPI);
        AHBPrefetchEnable(FLEXSPI);
        return status;
    }

    flashXfer.deviceAddress = address;
    flashXfer.port = kFLEXSPI_PortA1;
    flashXfer.cmdType = kFLEXSPI_Command;
    flashXfer.SeqNumber = 1;
    flashXfer.seqIndex = NOR_CMD_LUT_SEQ_IDX_ERASESECTOR;
    status = FLEXSPI_TransferBlockingRamfunc(base, &flashXfer);

    if (status != kStatus_Success)
    {
        FLEXSPI_SoftwareResetRamfunc(FLEXSPI);
        AHBPrefetchEnable(FLEXSPI);
        return status;
    }

    status = flexspi_nor_wait_bus_busy(base);

    FLEXSPI_SoftwareResetRamfunc(FLEXSPI);

    AHBPrefetchEnable(FLEXSPI);

    return status;
}

AT_QUICKACCESS_SECTION_CODE(status_t flexspi_nor_flash_page_program_byte(FLEXSPI_Type *base, uint32_t dstAddr, uint8_t *src,uint32_t size))
{
    status_t result = kStatus_Success;

    AHBPrefetchDisable(FLEXSPI);

    while (!((base->STS0 & FLEXSPI_STS0_ARBIDLE_MASK) && (base->STS0 & FLEXSPI_STS0_SEQIDLE_MASK)))
    {
    }

    /* Write neable */
    result = flexspi_nor_write_enable(base, dstAddr);

    if (result != kStatus_Success)
    {
        FLEXSPI_SoftwareResetRamfunc(FLEXSPI);
        AHBPrefetchEnable(FLEXSPI);
        return result;
    }

	  uint32_t configValue = 0;


    /* Clear sequence pointer before sending data to external devices. */
    base->FLSHCR2[kFLEXSPI_PortA1] |= FLEXSPI_FLSHCR2_CLRINSTRPTR_MASK;

    /* Clear former pending status before start this tranfer. */
    base->INTR |= FLEXSPI_INTR_AHBCMDERR_MASK | FLEXSPI_INTR_IPCMDERR_MASK | FLEXSPI_INTR_AHBCMDGE_MASK |
                  FLEXSPI_INTR_IPCMDGE_MASK;

    /* Configure base addresss. */
    base->IPCR0 = dstAddr;

    /* Reset fifos. */
    base->IPTXFCR |= FLEXSPI_IPTXFCR_CLRIPTXF_MASK;
    base->IPRXFCR |= FLEXSPI_IPRXFCR_CLRIPRXF_MASK;

    /* Configure data size. */
    configValue = FLEXSPI_IPCR1_IDATSZ(size);

    /* Configure sequence ID. */
    configValue |= FLEXSPI_IPCR1_ISEQID(NOR_CMD_LUT_SEQ_IDX_PAGEPROGRAM_SINGLE) | FLEXSPI_IPCR1_ISEQNUM(0);
    base->IPCR1 = configValue;

    /* Start Transfer. */
    base->IPCMD |= FLEXSPI_IPCMD_TRG_MASK;

    uint8_t txWatermark = ((base->IPTXFCR & FLEXSPI_IPTXFCR_TXWMRK_MASK) >> FLEXSPI_IPTXFCR_TXWMRK_SHIFT) + 1;
    uint32_t status;
    uint32_t i;
    uint8_t *buffer;
    uint8_t *FlexReg;
    buffer = (uint8_t *)src;

    /* Send data buffer */
    while (size)
    {
        /* Wait until there is room in the fifo. This also checks for errors. */
        while (!((status = base->INTR) & kFLEXSPI_IpTxFifoWatermarkEmpltyFlag))
        {
        }

        result = FLEXSPI_CheckAndClearErrorRamfunc(base, status);

        if (result)
        {
            FLEXSPI_SoftwareResetRamfunc(FLEXSPI);
            AHBPrefetchEnable(FLEXSPI);
            return result;
        }
        FlexReg = (uint8_t *)&(base->TFDR[0]);
        /* Write watermark level data into tx fifo . */
        if (size >= 8 * txWatermark)
        {
            for (i = 0; i < 8 * txWatermark; i++)
            {
                 *FlexReg++ = *buffer++;
            }

            size = size - 8 * txWatermark;
        }
        else
        {
            for (i = 0; i < (size); i++)
            {
                *FlexReg++ = *buffer++;
            }
            size = 0;
        }

        /* Push a watermark level datas into IP TX FIFO. */
        base->INTR |= kFLEXSPI_IpTxFifoWatermarkEmpltyFlag;
    }

    /* Wait for bus idle. */
    while (!((base->STS0 & FLEXSPI_STS0_ARBIDLE_MASK) && (base->STS0 & FLEXSPI_STS0_SEQIDLE_MASK)))
    {
    }

    result = flexspi_nor_wait_bus_busy(base);

    FLEXSPI_SoftwareResetRamfunc(FLEXSPI);

    AHBPrefetchEnable(FLEXSPI);

    return result;
}


AT_QUICKACCESS_SECTION_CODE(status_t flexspi_nor_flash_page_program(FLEXSPI_Type *base, uint32_t dstAddr, uint32_t *src, uint32_t size))
{
    status_t status;
    flexspi_transfer_t flashXfer;

    AHBPrefetchDisable(FLEXSPI);

    /* Write enable */
    status = flexspi_nor_write_enable(base, dstAddr);

    if (status != kStatus_Success)
    {
        FLEXSPI_SoftwareResetRamfunc(FLEXSPI);
        AHBPrefetchEnable(FLEXSPI);
        return status;
    }

    /* Prepare page program command */
    flashXfer.deviceAddress = dstAddr;
    flashXfer.port = kFLEXSPI_PortA1;
    flashXfer.cmdType = kFLEXSPI_Write;
    flashXfer.SeqNumber = 1;
    flashXfer.seqIndex = NOR_CMD_LUT_SEQ_IDX_PAGEPROGRAM_SINGLE;
    flashXfer.data = (uint32_t *)src;
    flashXfer.dataSize = size;
    status = FLEXSPI_TransferBlockingRamfunc(base, &flashXfer);

    if (status != kStatus_Success)
    {
        FLEXSPI_SoftwareResetRamfunc(FLEXSPI);
        AHBPrefetchEnable(FLEXSPI);
        return status;
    }

    status = flexspi_nor_wait_bus_busy(base);
    FLEXSPI_SoftwareResetRamfunc(FLEXSPI);
    AHBPrefetchEnable(FLEXSPI);

    return status;
}
AT_QUICKACCESS_SECTION_CODE(status_t flexspi_nor_flash_read(FLEXSPI_Type *base, uint32_t dstAddr, uint32_t *src, uint32_t size))
{
    status_t status;
    flexspi_transfer_t flashXfer;

    AHBPrefetchDisable(FLEXSPI);
    /* Prepare page program command */
    flashXfer.deviceAddress = dstAddr;
    flashXfer.port = kFLEXSPI_PortA1;
    flashXfer.cmdType = kFLEXSPI_Read;
    flashXfer.SeqNumber = 1;
    flashXfer.seqIndex = NOR_CMD_LUT_SEQ_IDX_READ_FAST_QUAD;
    flashXfer.data = (uint32_t *)src;
    flashXfer.dataSize = size;
    status = FLEXSPI_TransferBlockingRamfunc(base, &flashXfer);

    if (status != kStatus_Success)
    {
        FLEXSPI_SoftwareResetRamfunc(FLEXSPI);
        AHBPrefetchEnable(FLEXSPI);
        return status;
    }

    status = flexspi_nor_wait_bus_busy(base);
    FLEXSPI_SoftwareResetRamfunc(FLEXSPI);
    AHBPrefetchEnable(FLEXSPI);
    return status;
}
status_t flexspi_nor_get_vendor_id(FLEXSPI_Type *base, uint8_t *vendorId)
{
    uint32_t temp;
    flexspi_transfer_t flashXfer;
    flashXfer.deviceAddress = 0;
    flashXfer.port = kFLEXSPI_PortA1;
    flashXfer.cmdType = kFLEXSPI_Read;
    flashXfer.SeqNumber = 1;
    flashXfer.seqIndex = NOR_CMD_LUT_SEQ_IDX_READID;
    flashXfer.data = &temp;
    flashXfer.dataSize = 1;

    status_t status = FLEXSPI_TransferBlocking(base, &flashXfer);

    *vendorId = temp;

    return status;
}
