#include "is25lp064a_qspi.h"
#include "is25lp064a.h"
#include "qspi_status.h"
#include "stm32h7xx_hal.h"
#include <stdint.h>

#define MEMORY_FLASH_SIZE 0x800000 /* 8  MBytes*/
#define MEMORY_SECTOR_SIZE 0x1000  /* 4  KBytes */
#define MEMORY_PAGE_SIZE 0x100     /* 256 bytes */

extern QSPI_HandleTypeDef _qspi_flash;

static uint8_t qspi_enabled = 0;

static uint8_t QSPI_Wait(QSPI_AutoPollingTypeDef *config, uint32_t timeout) {

  QSPI_CommandTypeDef sCommand = {0};

  if (qspi_enabled) {
    sCommand.InstructionMode = QSPI_INSTRUCTION_4_LINES;
    sCommand.DataMode = QSPI_DATA_4_LINES;
    // Based on Reference manual RM0433 for the STM32H750 Value line,
    // dummy cycles needed on all read operations in QUAD mode
    sCommand.DummyCycles = IS25LP064A_DUMMY_CYCLES_READ_QUAD;
  } else {
    sCommand.InstructionMode = QSPI_INSTRUCTION_1_LINE;
    sCommand.DataMode = QSPI_DATA_1_LINE;
    sCommand.DummyCycles = 0;
  }
  sCommand.Instruction = READ_STATUS_REG_CMD;
  sCommand.AddressMode = QSPI_ADDRESS_NONE;
  sCommand.AlternateByteMode = QSPI_ALTERNATE_BYTES_NONE;
  ;
  sCommand.SIOOMode = QSPI_SIOO_INST_EVERY_CMD;

  if (HAL_QSPI_AutoPolling(&_qspi_flash, &sCommand, config, timeout) !=
      HAL_OK) {
    return qspi_ERROR;
  }

  return qspi_OK;
}


static uint8_t QSPI_ReadStatusRegister(uint8_t *status) {
  QSPI_CommandTypeDef sCommand = {0};

  if (qspi_enabled) {
    sCommand.InstructionMode = QSPI_INSTRUCTION_4_LINES;
    sCommand.DataMode = QSPI_DATA_4_LINES;
    // Based on Reference manual RM0433 for the STM32H750 Value line,
    // dummy cycles needed on all read operations in QUAD mode
    sCommand.DummyCycles = IS25LP064A_DUMMY_CYCLES_READ_QUAD;

  } else {
    sCommand.InstructionMode = QSPI_INSTRUCTION_1_LINE;
    sCommand.DataMode = QSPI_DATA_1_LINE;
    sCommand.DummyCycles = 0;
  }
  sCommand.Instruction = READ_STATUS_REG_CMD;
  sCommand.AddressSize = QSPI_ADDRESS_24_BITS;
  sCommand.AlternateByteMode = QSPI_ALTERNATE_BYTES_NONE;
  sCommand.SIOOMode = QSPI_SIOO_INST_EVERY_CMD;
  sCommand.AddressMode = QSPI_ADDRESS_NONE;
  sCommand.Address = 0;
  sCommand.NbData = 1;

  if (HAL_QSPI_Command(&_qspi_flash, &sCommand,
                       HAL_QPSI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) {
    return qspi_ERROR;
  }
  if (HAL_QSPI_Receive(&_qspi_flash, status, HAL_QPSI_TIMEOUT_DEFAULT_VALUE) !=
      HAL_OK) {
    return qspi_ERROR;
  }
  return qspi_OK;
}

static uint8_t QSPI_ResetChip(void) {
  QSPI_CommandTypeDef sCommand = {0};
  QSPI_AutoPollingTypeDef sConfig = {0};

  sCommand.InstructionMode = QSPI_INSTRUCTION_1_LINE;
  sCommand.AddressSize = QSPI_ADDRESS_24_BITS;
  sCommand.AlternateByteMode = QSPI_ALTERNATE_BYTES_NONE;
  sCommand.SIOOMode = QSPI_SIOO_INST_EVERY_CMD;
  sCommand.Instruction = RESET_ENABLE_CMD;
  sCommand.AddressMode = QSPI_ADDRESS_NONE;
  sCommand.Address = 0;
  sCommand.DataMode = QSPI_DATA_NONE;
  sCommand.DummyCycles = 0;

  if (HAL_QSPI_Command(&_qspi_flash, &sCommand,
                       HAL_QPSI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) {
    return qspi_ERROR;
  }

  sCommand.Instruction = RESET_MEMORY_CMD;

  if (HAL_QSPI_Command(&_qspi_flash, &sCommand,
                       HAL_QPSI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) {
    return qspi_ERROR;
  }

  sConfig.Match = 0;
  sConfig.Mask = IS25LP064A_SR_WIP;
  sConfig.MatchMode = QSPI_MATCH_MODE_AND;
  sConfig.StatusBytesSize = 1;
  sConfig.AutomaticStop = QSPI_AUTOMATIC_STOP_ENABLE;
  sConfig.Interval = 0x10;

  if (QSPI_Wait(&sConfig, HAL_QPSI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) {
    return qspi_ERROR;
  }

  return qspi_OK;
}

static uint8_t QSPI_WriteEnable(void) {
  QSPI_CommandTypeDef sCommand = {0};
  QSPI_AutoPollingTypeDef sConfig = {0};

  /* Enable write / erase operations */
  if (qspi_enabled) {
    sCommand.InstructionMode = QSPI_INSTRUCTION_4_LINES;
  } else {
    sCommand.InstructionMode = QSPI_INSTRUCTION_1_LINE;
  }
  sCommand.Instruction = WRITE_ENABLE_CMD;
  sCommand.AddressMode = QSPI_ADDRESS_NONE;
  sCommand.AlternateByteMode = QSPI_ALTERNATE_BYTES_NONE;
  sCommand.DataMode = QSPI_DATA_NONE;
  sCommand.DummyCycles = 0;
  sCommand.SIOOMode = QSPI_SIOO_INST_EVERY_CMD;

  if (HAL_QSPI_Command(&_qspi_flash, &sCommand,
                       HAL_QPSI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) {
    return qspi_ERROR;
  }

  /* Configure automatic polling mode to wait for write enabling */
  sConfig.Match = IS25LP064A_SR_WREN;
  sConfig.Mask = IS25LP064A_SR_WREN;
  sConfig.MatchMode = QSPI_MATCH_MODE_AND;
  sConfig.StatusBytesSize = 1;
  sConfig.AutomaticStop = QSPI_AUTOMATIC_STOP_ENABLE;
  sConfig.Interval = 0x10;

  if (QSPI_Wait(&sConfig, HAL_QPSI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) {
    return qspi_ERROR;
  }

  return qspi_OK;
}

/*Enable quad mode and set dummy cycles count*/
static uint8_t QSPI_Configuration(void) {

  QSPI_CommandTypeDef sCommand = {0};
  QSPI_AutoPollingTypeDef sConfig = {0};
  uint8_t reg = 0;

  sCommand.InstructionMode = QSPI_INSTRUCTION_1_LINE;
  sCommand.AlternateByteMode = QSPI_ALTERNATE_BYTES_NONE;
  sCommand.SIOOMode = QSPI_SIOO_INST_EVERY_CMD;
  sCommand.Instruction = WRITE_READ_PARAM_REG_CMD;
  sCommand.AddressMode = QSPI_ADDRESS_NONE;
  sCommand.DataMode = QSPI_DATA_1_LINE;
  sCommand.DummyCycles = 0;
  sCommand.NbData = 1;

  if (HAL_QSPI_Command(&_qspi_flash, &sCommand,
                       HAL_QPSI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) {
    return qspi_ERROR;
  }

  /* Minimum necessary dummy cycles for memory mapped mode at 100 MHz = 6
   * Setting in Read Register P4 P3 bits as 0 0, so full reg = 11100000 0xE0
   * see IS25LP064A data sheet section 6.3 READ REGISTER */
  reg = 0xE0;
  if (HAL_QSPI_Transmit(&_qspi_flash, &reg, HAL_QPSI_TIMEOUT_DEFAULT_VALUE) !=
      HAL_OK) {
    return qspi_ERROR;
  }

  sConfig.Match = 0;
  sConfig.Mask = IS25LP064A_SR_WIP;
  sConfig.MatchMode = QSPI_MATCH_MODE_AND;
  sConfig.StatusBytesSize = 1;
  sConfig.AutomaticStop = QSPI_AUTOMATIC_STOP_ENABLE;
  sConfig.Interval = 0x10;

  if (QSPI_Wait(&sConfig, HAL_QPSI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) {
    return qspi_ERROR;
  }

  /*----- Setting the QSPI mode ----*/

  /* Set the non-volatile Quad Enable bit in status register */
  sCommand.InstructionMode = QSPI_INSTRUCTION_1_LINE;
  sCommand.Instruction = WRITE_STATUS_REG_CMD;
  sCommand.AddressMode = QSPI_ADDRESS_NONE;
  sCommand.AlternateByteMode = QSPI_ALTERNATE_BYTES_NONE;
  sCommand.DataMode = QSPI_DATA_1_LINE;
  sCommand.DummyCycles = 0;
  sCommand.SIOOMode = QSPI_SIOO_INST_EVERY_CMD;
  sCommand.NbData = 1;

  if (QSPI_WriteEnable() != HAL_OK) {
    return qspi_ERROR;
  }

  if (HAL_QSPI_Command(&_qspi_flash, &sCommand,
                       HAL_QPSI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) {
    return qspi_ERROR;
  }

  reg = 0;
  if (QSPI_ReadStatusRegister(&reg) != HAL_OK) {
    return qspi_ERROR;
  }
  reg = reg | IS25LP064A_SR_QE;
  if (HAL_QSPI_Transmit(&_qspi_flash, &reg, HAL_QPSI_TIMEOUT_DEFAULT_VALUE) !=
      HAL_OK) {
    return qspi_ERROR;
  }
  /* Configure automatic polling mode to wait for quad enable complete */
  sConfig.Match = IS25LP064A_SR_QE;
  sConfig.Mask = IS25LP064A_SR_QE;

  if (QSPI_Wait(&sConfig, HAL_QPSI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) {
    return qspi_ERROR;
  }

  /* Wait to make sure controller is done with writing */
  sConfig.Match = 0;
  sConfig.Mask = IS25LP064A_SR_WIP;

  if (QSPI_Wait(&sConfig, HAL_QPSI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) {
    return qspi_ERROR;
  }

  /* Enter QPI mode */
  sCommand.InstructionMode = QSPI_INSTRUCTION_1_LINE;
  sCommand.Instruction = ENTER_QUAD_CMD;
  sCommand.AddressMode = QSPI_ADDRESS_NONE;
  sCommand.AlternateByteMode = QSPI_ALTERNATE_BYTES_NONE;
  sCommand.DataMode = QSPI_DATA_NONE;
  sCommand.DummyCycles = 0;
  sCommand.SIOOMode = QSPI_SIOO_INST_EVERY_CMD;
  sCommand.NbData = 0;

  if (HAL_QSPI_Command(&_qspi_flash, &sCommand,
                       HAL_QPSI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) {
    return qspi_ERROR;
  }
  qspi_enabled = 1; /* qpi mode ON */

  return qspi_OK;
}

uint8_t CSP_QSPI_Erase_Chip(void) {
  QSPI_CommandTypeDef sCommand = {0};
  QSPI_AutoPollingTypeDef sConfig = {0};

  if (QSPI_WriteEnable() != HAL_OK) {
    return qspi_ERROR;
  }

  sCommand.Instruction = EXT_CHIP_ERASE_CMD;
  sCommand.InstructionMode = QSPI_INSTRUCTION_4_LINES;
  sCommand.AddressSize = QSPI_ADDRESS_24_BITS;
  sCommand.AlternateByteMode = QSPI_ALTERNATE_BYTES_NONE;
  sCommand.SIOOMode = QSPI_SIOO_INST_EVERY_CMD;
  sCommand.AddressMode = QSPI_ADDRESS_NONE;
  sCommand.Address = 0;
  sCommand.DataMode = QSPI_DATA_NONE;
  sCommand.DummyCycles = 0;

  if (HAL_QSPI_Command(&_qspi_flash, &sCommand,
                       HAL_QPSI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) {
    return qspi_ERROR;
  }

  // Poll until the max chip erase time
  sConfig.Match = 0;
  sConfig.Mask = IS25LP064A_SR_WIP;
  sConfig.MatchMode = QSPI_MATCH_MODE_AND;
  sConfig.StatusBytesSize = 1;
  sConfig.AutomaticStop = QSPI_AUTOMATIC_STOP_ENABLE;
  sConfig.Interval = 0x10;

  if (QSPI_Wait(&sConfig, IS25LP064A_DIE_ERASE_MAX_TIME) != HAL_OK) {
    return qspi_ERROR;
  }

  return qspi_OK;
}

uint8_t CSP_QSPI_EraseSector(uint32_t EraseStartAddress,
                             uint32_t EraseEndAddress) {

  QSPI_CommandTypeDef sCommand = {0};
  QSPI_AutoPollingTypeDef sConfig = {0};

  /* Erasing Sequence -------------------------------------------------- */
  sCommand.InstructionMode = QSPI_INSTRUCTION_4_LINES;
  sCommand.AddressSize = QSPI_ADDRESS_24_BITS;
  sCommand.AlternateByteMode = QSPI_ALTERNATE_BYTES_NONE;
  sCommand.SIOOMode = QSPI_SIOO_INST_EVERY_CMD;
  sCommand.Instruction = SECTOR_ERASE_QPI_CMD;
  sCommand.AddressMode = QSPI_ADDRESS_4_LINES;
  sCommand.DataMode = QSPI_DATA_NONE;
  sCommand.DummyCycles = 0;

  sConfig.Match = 0;
  sConfig.Mask = IS25LP064A_SR_WIP;
  sConfig.MatchMode = QSPI_MATCH_MODE_AND;
  sConfig.StatusBytesSize = 1;
  sConfig.AutomaticStop = QSPI_AUTOMATIC_STOP_ENABLE;
  sConfig.Interval = 0x10;

  EraseStartAddress =
      EraseStartAddress - EraseStartAddress % IS25LP064A_SECTOR_SIZE;

  while (EraseEndAddress >= EraseStartAddress) {
    sCommand.Address = (EraseStartAddress & 0x7FFFFF);

    if (QSPI_WriteEnable() != HAL_OK) {
      return qspi_ERROR;
    }

    if (HAL_QSPI_Command(&_qspi_flash, &sCommand,
                         HAL_QPSI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) {
      return qspi_ERROR;
    }
    EraseStartAddress += IS25LP064A_SECTOR_SIZE;

    if (QSPI_Wait(&sConfig, HAL_QPSI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) {
      return qspi_ERROR;
    }
  }
  return qspi_OK;
}

uint8_t CSP_QSPI_EnableMemoryMappedMode(void) {

  QSPI_CommandTypeDef sCommand = {0};
  QSPI_MemoryMappedTypeDef sMemMappedCfg = {0};

  /* Enable Memory-Mapped mode
  The FRQIO instruction allows the address bits to be input four bits at a time.
  This may allow for code to be executed directly from the SPI in some
  applications. Sending the mode bits as AX (X = doesn't matter) will set the
  flash controller in memory mapped mode.
   */
  sCommand.InstructionMode = QSPI_INSTRUCTION_4_LINES;
  sCommand.Instruction = QUAD_INOUT_FAST_READ_CMD;
  sCommand.AddressSize = QSPI_ADDRESS_24_BITS;
  sCommand.AddressMode = QSPI_ADDRESS_4_LINES;
  sCommand.DataMode = QSPI_DATA_4_LINES;
  sCommand.NbData = 0;
  sCommand.Address = 0;

  sCommand.AlternateByteMode = QSPI_ALTERNATE_BYTES_4_LINES;
  sCommand.AlternateBytesSize = QSPI_ALTERNATE_BYTES_8_BITS;
  sCommand.AlternateBytes = 0x000000A0;
  sCommand.DummyCycles = IS25LP064A_DUMMY_CYCLES_READ_QUAD - 2;
  sCommand.SIOOMode = QSPI_SIOO_INST_ONLY_FIRST_CMD;

  sMemMappedCfg.TimeOutActivation = QSPI_TIMEOUT_COUNTER_DISABLE;

  if (HAL_QSPI_MemoryMapped(&_qspi_flash, &sCommand, &sMemMappedCfg) !=
      HAL_OK) {
    return qspi_ERROR;
  }
  return HAL_OK;
}

uint8_t CSP_QSPI_DisableMemoryMappedMode(void) {

  QSPI_CommandTypeDef sCommand = {0};
  uint8_t data;

  // Need to first stop the host controller's access to flash
  if (HAL_QSPI_Abort(&_qspi_flash) != HAL_OK) {
    return qspi_ERROR;
  }

  sCommand.InstructionMode = QSPI_INSTRUCTION_4_LINES;
  sCommand.Instruction = QUAD_INOUT_FAST_READ_CMD;
  sCommand.AddressSize = QSPI_ADDRESS_24_BITS;
  sCommand.AddressMode = QSPI_ADDRESS_4_LINES;
  sCommand.DataMode = QSPI_DATA_4_LINES;
  sCommand.NbData = 1;
  sCommand.Address = 0;
  sCommand.AlternateByteMode = QSPI_ALTERNATE_BYTES_4_LINES;
  sCommand.AlternateBytesSize = QSPI_ALTERNATE_BYTES_8_BITS;
  sCommand.AlternateBytes = 0x00000000;
  sCommand.DummyCycles = IS25LP064A_DUMMY_CYCLES_READ_QUAD;
  sCommand.SIOOMode = QSPI_SIOO_INST_ONLY_FIRST_CMD;

  if (HAL_QSPI_Command(&_qspi_flash, &sCommand,
                       HAL_QPSI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) {
    return qspi_ERROR;
  }

  if (HAL_QSPI_Receive(&_qspi_flash, &data, HAL_QPSI_TIMEOUT_DEFAULT_VALUE) !=
      HAL_OK) {
    return qspi_ERROR;
  }

  return qspi_OK;
}

uint8_t CSP_QSPI_Write(uint8_t *buffer, uint32_t address,
                       uint32_t buffer_size) {

  QSPI_CommandTypeDef sCommand = {0};
  QSPI_AutoPollingTypeDef sConfig = {0};
  uint32_t end_addr = 0, current_size = 0, current_addr = 0;

  /* Calculation of the size between the write address and the end of the page
   */
  current_addr = 0;

  while (current_addr <= address) {
    current_addr += IS25LP064A_PAGE_SIZE;
  }
  current_size = current_addr - address;

  /* Check if the size of the data is less than the remaining place in the page
   */
  if (current_size > buffer_size) {
    current_size = buffer_size;
  }

  /* Initialize the address variables */
  current_addr = address;
  end_addr = address + buffer_size;

  sCommand.InstructionMode = QSPI_INSTRUCTION_4_LINES;
  sCommand.AddressSize = QSPI_ADDRESS_24_BITS;
  sCommand.AlternateByteMode = QSPI_ALTERNATE_BYTES_NONE;
  sCommand.SIOOMode = QSPI_SIOO_INST_EVERY_CMD;
  sCommand.Instruction = PAGE_PROG_CMD;
  sCommand.AddressMode = QSPI_ADDRESS_4_LINES;
  sCommand.DataMode = QSPI_DATA_4_LINES;
  sCommand.NbData = buffer_size;
  sCommand.Address = address;
  sCommand.DummyCycles = 0;

  sConfig.Match = 0;
  sConfig.Mask = IS25LP064A_SR_WIP;
  sConfig.MatchMode = QSPI_MATCH_MODE_AND;
  sConfig.StatusBytesSize = 1;
  sConfig.AutomaticStop = QSPI_AUTOMATIC_STOP_ENABLE;
  sConfig.Interval = 0x10;

  /* Perform the write page by page */
  do {
    sCommand.Address = current_addr;
    sCommand.NbData = current_size;

    if (current_size == 0) {
      return HAL_OK;
    }

    /* Enable write operations */
    if (QSPI_WriteEnable() != HAL_OK) {
      return qspi_ERROR;
    }

    /* Configure the command */
    if (HAL_QSPI_Command(&_qspi_flash, &sCommand,
                         HAL_QPSI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) {

      return qspi_ERROR;
    }

    /* Transmission of the data */
    if (HAL_QSPI_Transmit(&_qspi_flash, buffer,
                          HAL_QPSI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) {

      return qspi_ERROR;
    }

    /* Configure automatic polling mode to wait for end of program */
    if (QSPI_Wait(&sConfig, HAL_QPSI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) {
      return qspi_ERROR;
    }

    /* Update the address and size variables for next page programming */
    current_addr += current_size;
    buffer += current_size;
    current_size = ((current_addr + IS25LP064A_PAGE_SIZE) > end_addr)
                       ? (end_addr - current_addr)
                       : IS25LP064A_PAGE_SIZE;
  } while (current_addr <= end_addr);

  return qspi_OK;
}

uint8_t CSP_QSPI_Read(uint8_t *buffer, uint32_t address, uint32_t buffer_size) {

  QSPI_CommandTypeDef sCommand = {0};

  sCommand.InstructionMode = QSPI_INSTRUCTION_4_LINES;
  sCommand.AddressSize = QSPI_ADDRESS_24_BITS;
  sCommand.SIOOMode = QSPI_SIOO_INST_EVERY_CMD;
  sCommand.Instruction = QUAD_INOUT_FAST_READ_CMD;
  sCommand.AddressMode = QSPI_ADDRESS_4_LINES;
  sCommand.DataMode = QSPI_DATA_4_LINES;
  sCommand.NbData = buffer_size;
  sCommand.Address = address;
  sCommand.DummyCycles = IS25LP064A_DUMMY_CYCLES_READ_QUAD;

  if (HAL_QSPI_Command(&_qspi_flash, &sCommand,
                       HAL_QPSI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) {

    return qspi_ERROR;
  }

  if (HAL_QSPI_Receive(&_qspi_flash, buffer, HAL_QPSI_TIMEOUT_DEFAULT_VALUE) !=
      HAL_OK) {

    return qspi_ERROR;
  }

  return qspi_OK;
}

//------------------------------------------------------
uint8_t CSP_QSPI_ExitQPIMODE(void) {
  QSPI_CommandTypeDef sCommand = {0};

  sCommand.InstructionMode = QSPI_INSTRUCTION_4_LINES;
  sCommand.AddressSize = QSPI_ADDRESS_24_BITS;
  sCommand.AlternateByteMode = QSPI_ALTERNATE_BYTES_NONE;
  sCommand.SIOOMode = QSPI_SIOO_INST_EVERY_CMD;
  sCommand.Instruction = EXIT_QUAD_CMD;
  sCommand.AddressMode = QSPI_ADDRESS_NONE;

  if (HAL_QSPI_Command(&_qspi_flash, &sCommand,
                       HAL_QPSI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) {
    return qspi_ERROR;
  }
  qspi_enabled = 0;

  return qspi_OK;
}

/* QUADSPI init function */
uint8_t CSP_QUADSPI_Init(void) {

  if (QSPI_ResetChip() != HAL_OK) {
    return qspi_ERROR;
  }

  if (QSPI_Configuration() != HAL_OK) {
    return qspi_ERROR;
  }

  return qspi_OK;
}

/* USER CODE END 1 */
