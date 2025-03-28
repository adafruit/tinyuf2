#include "board_api.h"
#include "stm32h7xx_hal.h"
#include "qspi_status.h"

#ifdef W25Qx_SPI
#include "components/w25qxx/w25qxx.h"
#endif // W25Qx_SPI

#ifdef W25Qx_QSPI
#include "components/w25qxx/w25qxx_qspi.h"
#endif // W25Qx_QSPI

#ifdef IS25LP064A
#include "components/is25lp064a/is25lp064a_qspi.h"
#include "components/is25lp064a/is25lp064a.h"
#endif

#if defined (BOARD_QSPI_FLASH_EN) && (BOARD_QSPI_FLASH_EN == 1)
QSPI_HandleTypeDef _qspi_flash;
#endif // BOARD_QSPI_FLASH_EN

#if defined (BOARD_SPI_FLASH_EN) && (BOARD_SPI_FLASH_EN == 1)
SPI_HandleTypeDef _spi_flash;
#endif // BOARD_SPI_FLASH_EN

//--------------------------------------------------------------------+
// Board Memory Callouts
//--------------------------------------------------------------------+
#ifdef W25Qx_SPI
uint32_t W25Qx_SPI_Transmit(uint8_t * buffer, uint16_t len, uint32_t timeout)
{
  return (uint32_t) HAL_SPI_Transmit(&_spi_flash, buffer, len, timeout);
}

uint32_t W25Qx_SPI_Receive(uint8_t * buffer, uint16_t len, uint32_t timeout)
{
  return (uint32_t) HAL_SPI_Receive(&_spi_flash, buffer, len, timeout);
}

void W25Qx_Delay(uint32_t ms)
{
  HAL_Delay(ms);
}

uint32_t W25Qx_GetTick(void)
{
  return HAL_GetTick();
}
#endif // W25Qx_SPI

//--------------------------------------------------------------------+
// Flash LL for tinyuf2
//--------------------------------------------------------------------+


extern volatile uint32_t _board_tmp_boot_addr[];
extern volatile uint32_t _board_tmp_boot_magic[];

#define TMP_BOOT_ADDR   _board_tmp_boot_addr[0]
#define TMP_BOOT_MAGIC  _board_tmp_boot_magic[0]

static void qspi_Init(void) {
  #ifdef W25Qx_QSPI
  w25qxx_Init();
  #endif
  #ifdef IS25LP064A
  CSP_QSPI_DisableMemoryMappedMode();
  CSP_QSPI_ExitQPIMODE();
  if (CSP_QUADSPI_Init() != qspi_OK) {
    TUF2_LOG1("Error initializing QSPI Flash\r\n");
  }
  #endif

}

static void qspi_EnterQPI(void) {
  #ifdef W25Qx_QSPI
  w25qxx_EnterQPI();
  #endif
}

static void qspi_Startup(void) {
  #ifdef W25Qx_QSPI
  w25qxx_Startup(qspi_DTRMode);
  #endif
  #ifdef IS25LP064A
  if (CSP_QSPI_EnableMemoryMappedMode() != qspi_OK) {
    TUF2_LOG1("Error enabling memory map for QSPI Flash\r\n");
  }
  #endif
}

static uint8_t qspi_Read(uint8_t *pData, uint32_t ReadAddr, uint32_t Size) {
  #ifdef W25Qx_QSPI
  return w25qxx_Read(pData,ReadAddr,Size);
  #endif
  #ifdef IS25LP064A
  return CSP_QSPI_Read(pData, ReadAddr, Size);
  #endif
  return qspi_OK;
}

static uint8_t qspi_Write(uint8_t* pData, uint32_t WriteAddr, uint32_t Size) {
  #ifdef W25Qx_QSPI
  return w25qxx_Write(pData,WriteAddr,Size);
  #endif
  #ifdef IS25LP064A
  return CSP_QSPI_Write(pData,WriteAddr,Size);
  #endif
  return qspi_OK;
}


static void qspi_EraseChip(void) {
  #ifdef W25Qx_QSPI
  w25qxx_EraseChip();
  #endif
  #ifdef IS25LP064A
  CSP_QSPI_Erase_Chip();
  #endif
}

uint32_t board_get_app_start_address(void)
{
  if (TMP_BOOT_MAGIC == 0xDEADBEEFU)
  {
    return TMP_BOOT_ADDR;
  }
  else
  {
    return BOARD_QSPI_APP_ADDR;
  }
}

void board_save_app_start_address(uint32_t addr)
{
  TMP_BOOT_MAGIC = 0xDEADBEEFU;
  TMP_BOOT_ADDR = addr;
}

void board_clear_temp_boot_addr(void)
{
  TMP_BOOT_MAGIC = 0x00U;
  TMP_BOOT_ADDR = 0x00U;
}

void board_flash_early_init(void)
{
#if defined (BOARD_QSPI_FLASH_EN) && (BOARD_QSPI_FLASH_EN == 1)
  // QSPI is initialized early to check for executable code
  qspi_flash_init(&_qspi_flash);
  // Initialize QSPI driver
  qspi_Init();
  // SPI -> QPI
  qspi_EnterQPI();
#endif // BOARD_QSPI_FLASH_EN
}

void board_flash_init(void)
{
#if defined (BOARD_SPI_FLASH_EN) && (BOARD_SPI_FLASH_EN == 1)
  // Initialize SPI peripheral
  spi_flash_init(&_spi_flash);
  // Initialize SPI drivers
  W25Qx_Init();
#endif // BOARD_SPI_FLASH_EN
}

void board_flash_deinit(void)
{
#if defined (BOARD_QSPI_FLASH_EN) && (BOARD_QSPI_FLASH_EN == 1)
  // Enable Memory Mapped Mode
  // QSPI flash will be available at 0x90000000U (readonly)
  qspi_Startup();
#endif // BOARD_QSPI_FLASH_EN
}

uint32_t board_flash_size(void)
{
  // TODO: how do we handle more than 1 target here?
  return 8*1024*1024;
}

void board_flash_flush(void)
{
  // TODO: do we need to implement this if there no caching involved?
  // maybe flush cached RAM here?
}

void board_flash_read(uint32_t addr, void * data, uint32_t len)
{
  TUF2_LOG1("Reading %lu byte(s) from 0x%08lx\r\n", len, addr);
#if defined (BOARD_QSPI_FLASH_EN) && (BOARD_QSPI_FLASH_EN == 1)
  // addr += QSPI_BASE_ADDR;
  if (IS_QSPI_ADDR(addr))
  {
    (void) qspi_Read(data, addr - QSPI_BASE_ADDR, len);
    return;
  }
#endif

#if defined (BOARD_AXISRAM_EN) && (BOARD_AXISRAM_EN == 1)
  if (IS_AXISRAM_ADDR(addr) && IS_AXISRAM_ADDR(addr + len - 1))
  {
    memcpy(data, (void *) addr, len);
    return;
  }
#endif // BOARD_AXISRAM_EN

  if (IS_PFLASH_ADDR(addr))
  {
    memcpy(data, (void *) addr, len);
    return;
  }

  {
    // Invalid address read
    __asm("bkpt #3");
  }
}

bool board_flash_write(uint32_t addr, void const * data, uint32_t len)
{
  TUF2_LOG1("Programming %lu byte(s) at 0x%08lx\r\n", len, addr);

  // For external flash
  // TODO: these should be configurable parameters
  // Page size = 256 bytes
  // Sector size = 4K bytes
#if defined (BOARD_SPI_FLASH_EN) && (BOARD_SPI_FLASH_EN == 1U)
  if (IS_SPI_ADDR(addr) && IS_SPI_ADDR(addr + len - 1))
  {
    W25Qx_Write((uint8_t *) data, (addr - SPI_BASE_ADDR), len);
    return true;
  }
#endif

#if defined (BOARD_QSPI_FLASH_EN) && (BOARD_QSPI_FLASH_EN == 1)
  if (IS_QSPI_ADDR(addr) && IS_QSPI_ADDR(addr + len - 1))
  {
    // SET_BOOT_ADDR(BOARD_AXISRAM_APP_ADDR);
    // handles erasing internally
    #ifdef IS25LP064A
    // flash needs to be erased before writing
    if (addr % IS25LP064A_SECTOR_SIZE == 0) {
      // erase 4k sector ahead of next page writes
      if (CSP_QSPI_EraseSector(addr, addr+IS25LP064A_SECTOR_SIZE) != qspi_OK) {
        TUF2_LOG1("Error erasing sector at address: %lx \r\n",addr);
      }
    }
    #endif
    if (qspi_Write((uint8_t *)data, (addr - QSPI_BASE_ADDR), len) != qspi_OK)
    {
      TUF2_LOG1("Error QSPI Flash write\r\n");
      __asm("bkpt #9");
    }
    return true;
  }
#endif

#if defined (BOARD_AXISRAM_EN) && (BOARD_AXISRAM_EN == 1)
  if (IS_AXISRAM_ADDR(addr) && IS_AXISRAM_ADDR(addr + len - 1))
  {
    // This memory is cached, DCache is cleaned in dfu_complete
    SET_BOOT_ADDR(BOARD_AXISRAM_APP_ADDR);
    memcpy((void *) addr, data, len);
    return true;
  }
#endif // BOARD_AXISRAM_EN

  // This is not a good idea for the h750 port because
  // - There is only one flash bank available
  // - There is only one sector available
  // - It will also need a config section in flash to store the boot address
  if (IS_PFLASH_ADDR(addr) && IS_PFLASH_ADDR(addr + len - 1))
  {
    // TODO: Implement this
    // SET_BOOT_ADDR(BOARD_PFLASH_APP_ADDR);
    return false;
  }

  // Invalid address write
  __asm("bkpt #4");
  return false;
}

void board_flash_erase_app(void)
{
  board_flash_init();

#if defined (BOARD_QSPI_FLASH_EN) && (BOARD_QSPI_FLASH_EN == 1)
  TUF2_LOG1("Erasing QSPI Flash\r\n");
  // Erase QSPI Flash
  (void) qspi_EraseChip();
#endif

#if defined(BOARD_SPI_FLASH_EN) && (BOARD_SPI_FLASH_EN == 1)
  TUF2_LOG1("Erasing SPI Flash\r\n");
  // Erase QSPI Flash
  (void) W25Qx_Erase_Chip();
#endif

  // TODO: Implement PFLASH erase for non-tinyuf2 sectors
  board_reset();
}
