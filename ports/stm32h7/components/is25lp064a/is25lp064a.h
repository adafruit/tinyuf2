/*
 * IS25LP064A.h
 *
 * Adapted from https://github.com/electro-smith/libDaisy/blob/master/src/dev/flash_IS25LP064A.h
 *
 */

 #ifndef INC_FLASH_IS25LP064A_H_
 #define INC_FLASH_IS25LP064A_H_

 #ifdef __cplusplus
 extern "C" {
 #endif

 #define IS25LP064A_FLASH_SIZE 0x800000 /* 8  MBytes*/
 #define IS25LP064A_BLOCK_SIZE 0x10000  /* 64 KBytes */
 #define IS25LP064A_SECTOR_SIZE 0x1000  /* 4  KBytes */
 #define IS25LP064A_PAGE_SIZE 0x100     /* 256 bytes */

 #define IS25LP064A_SECTOR_COUNT 2048


 #define IS25LP064A_DUMMY_CYCLES_READ_QUAD 6     /* & */
 #define IS25LP064A_DUMMY_CYCLES_READ 6          /* & */
 //#define IS25LP064A_DUMMY_CYCLES_READ_DTR 6      /* & */
 //#define IS25LP064A_DUMMY_CYCLES_READ_QUAD_DTR 6 /* & */


 #define IS25LP064A_DIE_ERASE_MAX_TIME 46000 /* 45 max seconds in datasheet */
 #define IS25LP064A_BLOCK_ERASE_MAX_TIME 1100 /* 1000 ms max in datasheet */
 #define IS25LP064A_SECTOR_ERASE_MAX_TIME 350 /* 300 ms max in datasheet */


     /* Low Power Modes */
 #define ENTER_DEEP_POWER_DOWN 0XB9 /* & */
 #define EXIT_DEEP_POWER_DOWN 0XAB  /* Release from Power-down/Read Device ID instruction  */

     /* Software Reset Operation commands */
 #define RESET_ENABLE_CMD 0x66
 #define RESET_MEMORY_CMD 0x99 /* & */

     /* Identification Operations */
 #define READ_ID_CMD 0xAB  /* Release from Power-down/Read Device ID instruction  */
 #define READ_ID_CMD2 0x9F  /* JEDEC ID READ command in SPI mode */
 #define MULTIPLE_IO_READ_ID_CMD 0xAF /* JEDEC ID READ command in QPI mode  */
 #define READ_SERIAL_FLASH_DISCO_PARAM_CMD 0x5A /* Serial Flash Discoverable Parameters (SFDP) */
 #define READ_MANUFACT_AND_ID 0x90 /* Read Product Identification (RDID) instruction */
 #define READ_UNIQUE_ID 0x4B /* Read Unique ID Number (RDUID) */

 #define NO_OP 0x00 /* Cancels Reset Enable */

     /* Sector LOCK/UNLOCK Operations */
 #define SECTOR_UNLOCK 0x26 /**< & */
 #define SECTOR_LOCK 0x24   /**< & */

     /* Security Information Row */
 #define INFO_ROW_ERASE_CMD 0x64   /* Information Row Erase (IRER) instruction */
 #define INFO_ROW_PROGRAM_CMD 0x62 /* Information Row Program (IRP) instruction */
 #define INFO_ROW_READ_CMD 0x68    /* Information Row Read (IRRD) instruction */

     /* Read Operations */
 #define READ_CMD 0x03 /* NORMAL READ (NORD) instruction */

 #define FAST_READ_CMD 0x0B /* FAST READ (FRD) instruction for both 1 line and QPI modes */
 #define FAST_READ_DTR_CMD 0x0D /* FRDTR instruction */

 #define DUAL_OUT_FAST_READ_CMD 0x3B /* FAST READ DUAL OUTPUT OPERATION (FRDO) */

 #define DUAL_INOUT_FAST_READ_CMD 0xBB     /* FAST READ DUAL I/O OPERATION (FRDIO) */
 #define DUAL_INOUT_FAST_READ_DTR_CMD 0xBD /* FAST READ DUAL IO DTR MODE OPERATION (FRDDTR) */

 #define QUAD_OUT_FAST_READ_CMD 0x6B /* FAST READ QUAD OUTPUT OPERATION (FRQO) */

 #define QUAD_INOUT_FAST_READ_CMD 0xEB     /* FAST READ QUAD I/O OPERATION (FRQIO) - can be used to enable memory mapped mode */
 #define QUAD_INOUT_FAST_READ_DTR_CMD 0xED /* FAST READ QUAD IO DTR MODE OPERATION (FRQDTR) */

     /* Write Operations */
 #define WRITE_ENABLE_CMD 0x06  /* WRITE ENABLE OPERATION (WREN) */
 #define WRITE_DISABLE_CMD 0x04 /* WRITE DISABLE OPERATION (WRDI) */

     /* Register Operations */
 #define READ_STATUS_REG_CMD 0x05  /* READ STATUS REGISTER OPERATION (RDSR) */
 #define WRITE_STATUS_REG_CMD 0x01 /* WRITE STATUS REGISTER OPERATION (WRSR) */

 #define READ_FUNCTION_REGISTER 0X48  /*  READ FUNCTION REGISTER OPERATION (RDFR) */
 #define WRITE_FUNCTION_REGISTER 0x42 /* WRITE FUNCTION REGISTER OPERATION (WRFR) */

 #define WRITE_READ_PARAM_REG_CMD 0xC0 /* SET READ PARAMETERS OPERATION (SRP) */

     /* Page Program Operations */
 #define PAGE_PROG_CMD 0x02  /* PAGE PROGRAM OPERATION (PP) */

     /* QUAD INPUT PAGE PROGRAM OPERATION (PPQ) */
 #define QUAD_IN_PAGE_PROG_CMD 0x32
 #define EXT_QUAD_IN_PAGE_PROG_CMD 0x38

     /* Erase Operations */
 #define SECTOR_ERASE_CMD 0xd7  /* SECTOR ERASE OPERATION (S E R) on SPI */
 #define SECTOR_ERASE_QPI_CMD 0x20 /* SECTOR ERASE OPERATION (S E R) QPI */

 #define BLOCK_ERASE_CMD 0xD8     /* BLOCK ERASE OPERATION (BER64K) */
 #define BLOCK_ERASE_32K_CMD 0x52 /* BLOCK ERASE OPERATION (BER32K) */

 #define CHIP_ERASE_CMD 0xC7     /* CHIP ERASE OPERATION (CER) on SPI */
 #define EXT_CHIP_ERASE_CMD 0x60 /* CHIP ERASE OPERATION (CER) on QPI*/

 #define PROG_ERASE_RESUME_CMD 0x7A     /* Resume program/erase (PERRSM) on SPI */
 #define EXT_PROG_ERASE_RESUME_CMD 0x30 /* Resume program/erase (PERRSM) on QPI */

 #define PROG_ERASE_SUSPEND_CMD 0x75     /* Suspend during program/erase (PERSUS) on SPI */
 #define EXT_PROG_ERASE_SUSPEND_CMD 0xB0 /* Suspend during program/erase (PERSUS) on QPI */

     /** Quad Operations */
 #define ENTER_QUAD_CMD 0x35 /* ENTER QUAD PERIPHERAL INTERFACE (QPI) MODE OPERATION (QIOEN) */
 #define EXIT_QUAD_CMD 0xF5 /* EXIT QUAD PERIPHERAL INTERFACE (QPI) MODE OPERATION (QIODI) */


     /* Status Register */
 #define IS25LP064A_SR_WIP ((uint8_t)0x01)  /* WIP Write in progress */
 #define IS25LP064A_SR_WREN ((uint8_t)0x02) /* W E L Write enable latch */
 //#define IS25LP064A_SR_BLOCKPR                  ((uint8_t)0x5C)    /*!< Block protected against program and erase operations */
 //#define IS25LP064A_SR_PRBOTTOM                 ((uint8_t)0x20)    /*!< Protected memory area defined by BLOCKPR starts from top or bottom */
 #define IS25LP064A_SR_QE ((uint8_t)0x40) /* QE Quad Enable */
 #define IS25LP064A_SR_SRWREN ((uint8_t)0x80) /* SRWD Status Register Write Disable*/

 #ifdef __cplusplus
 }
 #endif

 #endif /* INC_FLASH_IS25LP064A_H_ */
