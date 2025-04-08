#ifndef __IS25LP064A_QSPI_H
#define __IS25LP064A_QSPI_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>

uint8_t CSP_QUADSPI_Init(void);
uint8_t CSP_QSPI_Erase_Chip(void);
uint8_t CSP_QSPI_EraseSector(uint32_t EraseStartAddress,
                             uint32_t EraseEndAddress);
uint8_t CSP_QSPI_EnableMemoryMappedMode(void);
uint8_t CSP_QSPI_DisableMemoryMappedMode(void);
uint8_t CSP_QSPI_Write(uint8_t *buffer, uint32_t address, uint32_t buffer_size);
uint8_t CSP_QSPI_Read(uint8_t *buffer, uint32_t address, uint32_t buffer_size);
//---------------------------------------------
uint8_t CSP_QSPI_ExitQPIMODE(void);

/* USER CODE END Private defines */


/* USER CODE BEGIN Prototypes */

#ifdef __cplusplus
}
#endif

#endif
