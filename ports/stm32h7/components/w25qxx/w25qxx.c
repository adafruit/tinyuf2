#include "w25qxx.h"
#include "board_api.h"

W25Qx_Parameter W25Qx_Para;

static void	W25Qx_Reset(void);

/**
  * @brief  Initializes the W25QXXXX interface.
  * @retval None
  */
uint8_t W25Qx_Init(void)
{
  uint8_t state;
  /* Reset W25Qxxx */
  W25Qx_Reset();
  W25Qx_Delay(5);
  state = W25Qx_Get_Parameter(&W25Qx_Para);
  return state;
}

/**
  * @brief  This function reset the W25Qx.
  * @retval None
  */
static void	W25Qx_Reset(void)
{
  uint8_t cmd[2] = {RESET_ENABLE_CMD,RESET_MEMORY_CMD};

  SPI_FLASH_EN();
  /* Send the reset command */
  W25Qx_SPI_Transmit(cmd, 2, W25QXXXX_TIMEOUT_VALUE);
  SPI_FLASH_DIS();

}

/**
  * @brief  Reads current status of the W25QXXXX.
  * @retval W25QXXXX memory status
  */
static uint8_t W25Qx_GetStatus(void)
{
  uint8_t cmd[] = {READ_STATUS_REG1_CMD};
  uint8_t status;

  SPI_FLASH_EN();

  /* Send the read status command */
  W25Qx_SPI_Transmit(cmd, 1, W25QXXXX_TIMEOUT_VALUE);
  /* Reception of the data */
  W25Qx_SPI_Receive(&status, 1, W25QXXXX_TIMEOUT_VALUE);
  SPI_FLASH_DIS();

  /* Check the value of the register */
  if((status & W25QXXXX_FSR_BUSY) != 0)
  {
    return W25Qx_BUSY;
  }
  else
  {
    return W25Qx_OK;
  }
}

/**
  * @brief  This function send a Write Enable and wait it is effective.
  * @retval None
  */
uint8_t W25Qx_WriteEnable(void)
{
  uint8_t cmd[] = {WRITE_ENABLE_CMD};
  uint32_t tickstart = W25Qx_GetTick();

  /*Select the FLASH: Chip Select low */
  SPI_FLASH_EN();
  /* Send the read ID command */
  W25Qx_SPI_Transmit(cmd, 1, W25QXXXX_TIMEOUT_VALUE);
  /*Deselect the FLASH: Chip Select high */
  SPI_FLASH_DIS();

  /* Wait the end of Flash writing */
  while(W25Qx_GetStatus() == W25Qx_BUSY)
  {
    /* Check for the Timeout */
    if((W25Qx_GetTick() - tickstart) > W25QXXXX_TIMEOUT_VALUE)
    {
      return W25Qx_TIMEOUT;
    }
    W25Qx_Delay(1);
  }

  return W25Qx_OK;
}

/**
  * @brief  Read Manufacture/Device ID.
  * @param  return value address
/   返回值如下:
/   0XEF13,表示芯片型号为W25Q80
/   0XEF14,表示芯片型号为W25Q16
/   0XEF15,表示芯片型号为W25Q32
/   0XEF16,表示芯片型号为W25Q64
  * @retval None
  */
void W25Qx_Read_ID(uint16_t *ID)
{
  uint8_t idt[2];

  uint8_t cmd[4] = {READ_ID_CMD,0x00,0x00,0x00};

  SPI_FLASH_EN();
  /* Send the read ID command */
  W25Qx_SPI_Transmit(cmd, 4, W25QXXXX_TIMEOUT_VALUE);
  /* Reception of the data */
  W25Qx_SPI_Receive(idt, 2, W25QXXXX_TIMEOUT_VALUE);

  *ID = (idt[0] << 8) + idt[1];

  SPI_FLASH_DIS();

}

#include <math.h>
/**
  * @brief  Get W25QX Parameter.
  * @param  Para: W25Qx_Parameter
  * @retval NULL
  */

uint8_t W25Qx_Get_Parameter(W25Qx_Parameter *Para)
{
  uint16_t id;
  uint32_t size;

  Para->PAGE_SIZE = 256;
  Para->SUBSECTOR_SIZE = 4096;
  Para->SECTOR_SIZE = 0x10000;

  W25Qx_Read_ID(&id);
  if(id < W25Q80 || id > W25Q128) return W25Qx_ERROR;

  size = (uint32_t) powf(2,(id - 0xEF13)) * 1024 * 1024;

  Para->FLASH_Id = id;
  Para->FLASH_Size = size;
  Para->SUBSECTOR_COUNT = Para->FLASH_Size / Para->SUBSECTOR_SIZE;
  Para->SECTOR_COUNT = Para->FLASH_Size / Para->SECTOR_SIZE;

  return W25Qx_OK;
}
/**
  * @brief  Reads an amount of data from the QSPI memory.
  * @param  pData: Pointer to data to be read
  * @param  ReadAddr: Read start address
  * @param  Size: Size of data to read
  * @retval QSPI memory status
  */
uint8_t W25Qx_Read(uint8_t* pData, uint32_t ReadAddr, uint32_t Size)
{
  uint8_t cmd[4];

  /* Configure the command */
  cmd[0] = READ_CMD;
  cmd[1] = (uint8_t)(ReadAddr >> 16);
  cmd[2] = (uint8_t)(ReadAddr >> 8);
  cmd[3] = (uint8_t)(ReadAddr);

  SPI_FLASH_EN();
  /* Send the read ID command */
  W25Qx_SPI_Transmit(cmd, 4, W25QXXXX_TIMEOUT_VALUE);
  /* Reception of the data */
  if (W25Qx_SPI_Receive(pData,Size,W25QXXXX_TIMEOUT_VALUE) != 0U)
  {
    return W25Qx_ERROR;
  }
  SPI_FLASH_DIS();
  return W25Qx_OK;
}

/**
  * @brief  Writes an amount of data to the SPI memory.
  * @param  pData: Pointer to data to be written
  * @param  WriteAddr: Write start address
  * @param  Size: Size of data to write,No more than 256byte.
  * @retval SPI memory status
  */
uint8_t W25Qx_WriteNoCheck(uint8_t* pData, uint32_t WriteAddr, uint32_t Size)
{
  uint8_t cmd[4];
  uint32_t end_addr, current_size, current_addr;
  uint32_t tickstart = W25Qx_GetTick();

  /* Calculation of the size between the write address and the end of the page */
  current_addr = 0;

  while (current_addr <= WriteAddr)
  {
    current_addr += W25QXXXX_PAGE_SIZE;
  }
  current_size = current_addr - WriteAddr;

  /* Check if the size of the data is less than the remaining place in the page */
  if (current_size > Size)
  {
    current_size = Size;
  }

  /* Initialize the address variables */
  current_addr = WriteAddr;
  end_addr = WriteAddr + Size;

  /* Perform the write page by page */
  do
  {
    /* Configure the command */
    cmd[0] = PAGE_PROG_CMD;
    cmd[1] = (uint8_t)(current_addr >> 16);
    cmd[2] = (uint8_t)(current_addr >> 8);
    cmd[3] = (uint8_t)(current_addr);

    /* Enable write operations */
    W25Qx_WriteEnable();

    SPI_FLASH_EN();
    /* Send the command */
    if (W25Qx_SPI_Transmit(cmd, 4, W25QXXXX_TIMEOUT_VALUE) != 0U)
    {
      return W25Qx_ERROR;
    }

    /* Transmission of the data */
    if (W25Qx_SPI_Transmit(pData,current_size, W25QXXXX_TIMEOUT_VALUE) != 0U)
    {
      return W25Qx_ERROR;
    }
    SPI_FLASH_DIS();
      /* Wait the end of Flash writing */
    while(W25Qx_GetStatus() == W25Qx_BUSY)
    {
      /* Check for the Timeout */
      if((W25Qx_GetTick() - tickstart) > W25QXXXX_TIMEOUT_VALUE)
      {
        return W25Qx_TIMEOUT;
      }
      //delay(1);
    }

    /* Update the address and size variables for next page programming */
    current_addr += current_size;
    pData += current_size;
    current_size = ((current_addr + W25QXXXX_PAGE_SIZE) > end_addr) ? (end_addr - current_addr) : W25QXXXX_PAGE_SIZE;
  } while (current_addr < end_addr);


  return W25Qx_OK;
}

/**
  * @brief  Erases and Writes an amount of data to the SPI memory.
  * @param  pData: Pointer to data to be written
  * @param  WriteAddr: Write start address
  * @param  Size: Size of data to write,No more than 256byte.
  * @retval QSPI memory status
  */
uint8_t W25Qx_Write(uint8_t* pData, uint32_t WriteAddr, uint32_t Size)
{
  uint16_t idx;
  uint8_t buffer[4096u];
  uint32_t sector_pos = WriteAddr / 4096u; // sector pos for write
  uint32_t sector_offs = WriteAddr % 4096u; // write offset in sector
  uint32_t sector_avl = 4096u - sector_offs; // available space in sector
  if (Size <= sector_avl) sector_avl = Size;

  while (1)
  {
    if (W25Qx_OK != W25Qx_Read(buffer, sector_pos * 4096, 4096u)) {
      return W25Qx_ERROR;
    }

    for (idx = 0u; idx < sector_avl; idx += 1u)
    {
      if (buffer[sector_offs + idx] != 0xFFu) break;
    }

    if (idx < sector_avl)
    {
      // sector is not erased
      if (W25Qx_OK != W25Qx_Erase_Block(sector_pos * 4096))
      {
        return W25Qx_ERROR;
      }
      for (idx = 0u; idx < sector_avl; idx += 1u)
      {
        buffer[sector_offs + idx] = pData[idx];
      }
      (void) W25Qx_WriteNoCheck(buffer, sector_pos * 4096, 4096);
    }
    else
    {
      // sector is already erased
      (void) W25Qx_WriteNoCheck(pData, WriteAddr, sector_avl);
    }

    if (Size == sector_avl)
    {
      break;
    }
    else
    {
      sector_pos += 1u;
      sector_offs = 0u;
      pData += sector_avl;
      WriteAddr += sector_avl;
      Size -= sector_avl;
      sector_avl = (Size > 4096) ? 4096 : Size;
    }
  }

  return W25Qx_OK;
}

/**
  * @brief  Erases the specified block of the QSPI memory.
  * @param  BlockAddress: Block address to erase
  * @retval QSPI memory status
  */
uint8_t W25Qx_Erase_Block(uint32_t Address)
{
  uint8_t cmd[4];
  uint32_t tickstart = W25Qx_GetTick();
  cmd[0] = SECTOR_ERASE_CMD;
  cmd[1] = (uint8_t)(Address >> 16);
  cmd[2] = (uint8_t)(Address >> 8);
  cmd[3] = (uint8_t)(Address);

  /* Enable write operations */
  W25Qx_WriteEnable();

  /*Select the FLASH: Chip Select low */
  SPI_FLASH_EN();
  /* Send the read ID command */
  W25Qx_SPI_Transmit(cmd, 4, W25QXXXX_TIMEOUT_VALUE);
  /*Deselect the FLASH: Chip Select high */
  SPI_FLASH_DIS();

  /* Wait the end of Flash writing */
  while(W25Qx_GetStatus() == W25Qx_BUSY)
  {
    /* Check for the Timeout */
    if((W25Qx_GetTick() - tickstart) > W25QXXXX_SECTOR_ERASE_MAX_TIME)
    {
      return W25Qx_TIMEOUT;
    }
    //delay(1);
  }
  return W25Qx_OK;
}

/**
  * @brief  Erases the entire QSPI memory.This function will take a very long time.
  * @retval QSPI memory status
  */
uint8_t W25Qx_Erase_Chip(void)
{
  uint8_t cmd[4];
  uint32_t tickstart = W25Qx_GetTick();
  cmd[0] = CHIP_ERASE_CMD;

  /* Enable write operations */
  W25Qx_WriteEnable();

  /*Select the FLASH: Chip Select low */
  SPI_FLASH_EN();
  /* Send the read ID command */
  W25Qx_SPI_Transmit(cmd, 1, W25QXXXX_TIMEOUT_VALUE);
  /*Deselect the FLASH: Chip Select high */
  SPI_FLASH_DIS();

  /* Wait the end of Flash writing */
  while(W25Qx_GetStatus() == W25Qx_BUSY)
  {
    /* Check for the Timeout */
    if((W25Qx_GetTick() - tickstart) > W25QXXXX_BULK_ERASE_MAX_TIME)
    {
      return W25Qx_TIMEOUT;
    }
    //delay(1);
  }
  return W25Qx_OK;
}
