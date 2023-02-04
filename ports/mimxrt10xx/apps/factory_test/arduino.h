#include <stdlib.h>
#include <stdio.h>
#include <stdbool.h>
#include <string.h>
#include <stdarg.h>

#include "fsl_common.h"
#include "fsl_gpio.h"
#include "fsl_iomuxc.h"
#include "fsl_lpuart.h"
//#include "fsl_adc12.h"

#include "board_api.h"
#include "tusb.h"

#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2
#define LOW 0
#define HIGH 1


#define PIN_SDA 30
#define PIN_SCL 31
#define PIN_MOSI 32
#define PIN_MISO 33
#define PIN_SCK 34
#define AD0 14
#define AD1 15
#define AD2 16
#define AD3 17
#define AD4 18
#define AD5 19


typedef struct _pinmux {
  uint32_t muxReg;
  uint8_t muxMode;
  uint8_t inputReg;
  uint8_t idaisy;
  uint32_t configReg;
} pinmux;

typedef struct _pinmapping {
  uint8_t num;
  GPIO_Type *port;
  uint32_t pin;
  pinmux mux;
  ADC_Type *adc;
} pinmap;

void Serial_printf(const char format[], ...)  __attribute__ ((format (printf, 1, 0)));
uint32_t millis(void);
void delay(uint32_t ms);
void digitalWrite(uint32_t pinnum, bool value);
bool digitalRead(uint32_t pinnum);
void pinMode(uint32_t pinnum, uint8_t state);
