#ifndef QSPI_STATUS_H_
#define QSPI_STATUS_H_

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
  qspi_OK = 0x00,
  qspi_ERROR = 0x01,
  qspi_BUSY = 0x02,
  qspi_TIMEOUT = 0x03,

  qspi_QPIMode = 0x04,
  qspi_SPIMode = 0x05,

  qspi_DTRMode = 0x06,
  qspi_NormalMode = 0x07,

} qspi_StatusTypeDef;

#ifdef __cplusplus
}
#endif

#endif
