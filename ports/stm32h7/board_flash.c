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

#if defined(BOARD_PFLASH_APP_EN) && (BOARD_PFLASH_APP_EN == 1)
//--------------------------------------------------------------------+
// Internal flash application: 128KB sectors (8 per bank), 256-bit flash words
//--------------------------------------------------------------------+
#define PFLASH_WORD_SIZE (4 * FLASH_NB_32BITWORD_IN_FLASHWORD)

static bool _pflash_erased[BOARD_FLASH_SIZE / FLASH_SECTOR_SIZE];

static bool pflash_is_erased(uint32_t addr, uint32_t len)
{
  for (uint32_t i = 0; i < len; i += 4)
  {
    if (*(volatile uint32_t const *) (addr + i) != 0xFFFFFFFFU) return false;
  }
  return true;
}

// FLASH_CR1/SR1 drive the bank mapped at 0x08000000 also when SWAP_BANK swaps them (RM0433 Table 20)
static uint32_t pflash_bank(uint32_t addr)
{
  return (addr < FLASH_BANK2_BASE) ? FLASH_BANK_1 : FLASH_BANK_2;
}

// PGSERR and INCERR must be cleared before a new write (RM0433 4.3.9); the HAL samples the errors
// before waiting for the operation, so an error left by the last one fails the next HAL call
static void pflash_clear_errors(uint32_t bank)
{
  if (bank == FLASH_BANK_1)
  {
    __HAL_FLASH_CLEAR_FLAG_BANK1(FLASH_FLAG_ALL_ERRORS_BANK1);
  }
  else
  {
    __HAL_FLASH_CLEAR_FLAG_BANK2(FLASH_FLAG_ALL_ERRORS_BANK2);
  }
}

// Erase the sector holding addr unless it is blank, never the bootloader's
static bool pflash_erase_sector(uint32_t addr)
{
  uint32_t const sector_id = (addr - PFLASH_BASE_ADDR) / FLASH_SECTOR_SIZE;
  uint32_t const sector_addr = PFLASH_BASE_ADDR + sector_id * FLASH_SECTOR_SIZE;

  if (sector_addr < BOARD_FLASH_APP_START) return false;

  if (!pflash_is_erased(sector_addr, FLASH_SECTOR_SIZE))
  {
    uint32_t const bank = pflash_bank(sector_addr);
    FLASH_EraseInitTypeDef erase =
    {
      .TypeErase    = FLASH_TYPEERASE_SECTORS,
      .Banks        = bank,
      .Sector       = sector_id % FLASH_SECTOR_TOTAL,
      .NbSectors    = 1,
      .VoltageRange = FLASH_VOLTAGE_RANGE_4, // x64, the PSIZE reset value
    };
    uint32_t sector_error;

    TUF2_LOG1("Erase sector at 0x%08lx\r\n", sector_addr);
    pflash_clear_errors(bank);
    HAL_StatusTypeDef const status = HAL_FLASHEx_Erase(&erase, &sector_error);
    // flash is cached through the D-cache, drop the old content (RM0433 4.3.10)
    SCB_InvalidateDCache_by_Addr((void *) sector_addr, FLASH_SECTOR_SIZE);

    if (status != HAL_OK || !pflash_is_erased(sector_addr, FLASH_SECTOR_SIZE))
    {
      TUF2_LOG1("Error erasing sector at 0x%08lx\r\n", sector_addr);
      return false;
    }
  }

  _pflash_erased[sector_id] = true;
  return true;
}

static bool pflash_write_word(uint32_t dst, uint8_t const * src)
{
  // aligned copy: the HAL reads the source by 32-bit words
  uint32_t word[FLASH_NB_32BITWORD_IN_FLASHWORD];
  memcpy(word, src, sizeof(word));

  if (memcmp((void const *) dst, word, sizeof(word)) == 0) return true;

  // a flash word is programmed once per erase, a second write would corrupt its ECC
  if (!pflash_is_erased(dst, sizeof(word)))
  {
    TUF2_LOG1("Flash word at 0x%08lx is not erased\r\n", dst);
    return false;
  }

  pflash_clear_errors(pflash_bank(dst));
  HAL_StatusTypeDef const status = HAL_FLASH_Program(FLASH_TYPEPROGRAM_FLASHWORD, dst, (uint32_t) word);
  // the write-through store also updated a cached line, verify the flash itself
  SCB_InvalidateDCache_by_Addr((void *) dst, sizeof(word));

  if (status != HAL_OK || memcmp((void const *) dst, word, sizeof(word)) != 0)
  {
    TUF2_LOG1("Error programming flash at 0x%08lx\r\n", dst);
    return false;
  }
  return true;
}

static bool pflash_write(uint32_t addr, uint8_t const * data, uint32_t len)
{
  if ((addr % PFLASH_WORD_SIZE) || (len % PFLASH_WORD_SIZE)) return false;

  bool ok = (HAL_FLASH_Unlock() == HAL_OK);
  for (uint32_t offset = 0; ok && offset < len; offset += PFLASH_WORD_SIZE)
  {
    uint32_t const dst = addr + offset;
    uint32_t const sector_id = (dst - PFLASH_BASE_ADDR) / FLASH_SECTOR_SIZE;
    if (!_pflash_erased[sector_id])
    {
      ok = pflash_erase_sector(dst);
    }
    ok = ok && pflash_write_word(dst, data + offset);
  }
  HAL_FLASH_Lock();

  return ok;
}
#endif // BOARD_PFLASH_APP_EN

uint32_t board_get_app_start_address(void)
{
  if (TMP_BOOT_MAGIC == 0xDEADBEEFU)
  {
    return TMP_BOOT_ADDR;
  }
  else
  {
#if defined(BOARD_PFLASH_APP_EN) && (BOARD_PFLASH_APP_EN == 1)
    return BOARD_FLASH_APP_START;
#else
    return BOARD_QSPI_APP_ADDR;
#endif
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

#if defined(BOARD_PFLASH_APP_EN) && (BOARD_PFLASH_APP_EN == 1)
  memset(_pflash_erased, 0, sizeof(_pflash_erased));
#endif
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
#if defined(BOARD_PFLASH_APP_EN) && (BOARD_PFLASH_APP_EN == 1)
  return BOARD_FLASH_SIZE;
#else
  // TODO: how do we handle more than 1 target here?
  return 8*1024*1024;
#endif
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

#if defined(BOARD_PFLASH_APP_EN) && (BOARD_PFLASH_APP_EN == 1)
  if (IS_PFLASH_APP_RANGE(addr, len))
  {
    memcpy(data, (void *) addr, len);
    return;
  }
#endif

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

#if defined(BOARD_PFLASH_APP_EN) && (BOARD_PFLASH_APP_EN == 1)
  if (IS_PFLASH_APP_RANGE(addr, len))
  {
    return pflash_write(addr, data, len);
  }

  // the bootloader sector, or outside internal flash: e.g. a UF2 for an H750 board, same family ID
  TUF2_LOG1("Refusing write at 0x%08lx\r\n", addr);
  return false;
#else
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
#endif // BOARD_PFLASH_APP_EN
}

void board_flash_erase_app(void)
{
  board_flash_init();

#if defined(BOARD_PFLASH_APP_EN) && (BOARD_PFLASH_APP_EN == 1)
  // erasing the vector table's sector invalidates the app, the rest is erased when written
  TUF2_LOG1("Erasing application\r\n");
  if (HAL_FLASH_Unlock() == HAL_OK)
  {
    (void) pflash_erase_sector(BOARD_FLASH_APP_START);
  }
  HAL_FLASH_Lock();
#endif

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
