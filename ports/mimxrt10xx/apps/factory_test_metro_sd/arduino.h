#include <stdlib.h>
#include <stdio.h>
#include <stdbool.h>
#include <string.h>
#include <stdarg.h>

#include "fsl_common.h"
#include "fsl_gpio.h"
#include "fsl_iomuxc.h"
#include "fsl_lpuart.h"
#include "fsl_adc.h"

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

#define PIN_SD_CS 35
#define PIN_SD_DETECT 36

#define AD0 14
#define AD1 15
#define AD2 16
#define AD3 17
#define AD4 18
#define AD5 19

#define A0  AD0
#define A1  AD1
#define A2  AD2
#define A3  AD3
#define A4  AD4
#define A5  AD5


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
  uint8_t adc_channel;
  bool adc_inited; // inited as adc
} pinmap;

//void Serial_printf(const char format[], ...)  __attribute__ ((format (printf, 1, 0)));
uint32_t millis(void);
void delay(uint32_t ms);
void digitalWrite(uint32_t pinnum, bool value);
bool digitalRead(uint32_t pinnum);
int analogRead(uint32_t pinnum);
void pinMode(uint32_t pinnum, uint8_t state);
void setColor(uint32_t color);
uint32_t neoWheel(uint8_t WheelPos);
uint32_t makeColor(uint8_t r, uint8_t g, uint8_t b);

#define Serial_printf(...)    do { printf(__VA_ARGS__); tud_cdc_write_flush(); } while(0)
