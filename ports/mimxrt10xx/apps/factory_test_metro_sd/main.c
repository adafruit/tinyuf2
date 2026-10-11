/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2020 Ha Thach (tinyusb.org) for Adafruit Industries
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fsl_gpio.h"
#include "fsl_iomuxc.h"
#include "fsl_lpuart.h"
#include "fsl_lpspi.h"

#include "fsl_sdspi.h"

#include "arduino.h"
#include "board_api.h"
#include "tusb.h"

// This is an factory test for Metro M7 SD

// hathach: testing with Metro M7 Airlift without SD_CS and SD_DETECT. Use D2, D3 instead
//#define TESTING_WITH_AIRLIFT

#if defined TESTING_WITH_AIRLIFT
  #define SD_CS     3 // D3
  #define SD_DETECT 4 // D4
#else
  #define SD_CS     PIN_SD_CS
  #define SD_DETECT PIN_SD_DETECT
#endif

void loop(void);

static uint8_t all_pins[] = {
    0,       1,       2,        3,        4,       5,  6,
    7,       8,       9,        10,       11,      12, 13,
    PIN_SDA, PIN_SCL, PIN_MOSI, PIN_MISO, PIN_SCK, AD5
};

static bool test = false;
static bool run_sd_test = true;
static const uint8_t TEST_GPIO_POWER = 0xAE;
static const uint8_t TEST_GPIO_POWER_SD = 0xAF;
static const float DC_INPUT_MIN_VOLTS = 8.0f;
static const float DC_INPUT_MAX_VOLTS = 13.0f;

bool testpins(uint8_t a, uint8_t b, uint8_t *allpins, uint8_t num_allpins);
void test_print_adc(void);

bool test_sd(void);

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM DECLARATION
//--------------------------------------------------------------------+

int main(void) {
  board_init();
  board_uart_init(115200);

  board_timer_start(1);

  board_usb_init();
  tud_init(BOARD_TUD_RHPORT);

  setColor(0);
  pinMode(13, OUTPUT);

  while (1) {
    loop();
    // Failure messages may have no newline; drain libc before the USB FIFO.
    fflush(stdout);
    tud_task();
    tud_cdc_write_flush();

  }
}

uint8_t loopcount = 0;
void loop(void) {
  if (tud_cdc_available()) {
    uint8_t serial_buf[256];
    uint32_t count;

    count = tud_cdc_read(serial_buf, sizeof(serial_buf));
    if (count && (serial_buf[0] == TEST_GPIO_POWER || serial_buf[0] == TEST_GPIO_POWER_SD)) {
      run_sd_test = serial_buf[0] == TEST_GPIO_POWER_SD;
      test = true;
    }
  }

  if (!test) {
    setColor(neoWheel(loopcount++));

    if ((loopcount % 32) == 0) {
      digitalWrite(13, HIGH);
    }
    if ((loopcount % 32) == 16) {
      digitalWrite(13, LOW);
    }

    delay(10);
    return;
  }

  test = false; // Run one pass per start command, including failed passes.
  delay(100);
  Serial_printf("\n\r\n\rHello Metro M7 iMX RT1011 Test! %lu\n\r", millis());

  if (!testpins(0, 2, all_pins, sizeof(all_pins)))
    return;
  if (!testpins(1, 3, all_pins, sizeof(all_pins)))
    return;
  if (!testpins(4, 6, all_pins, sizeof(all_pins)))
    return;
  if (!testpins(5, 7, all_pins, sizeof(all_pins)))
    return;
  if (!testpins(8, 10, all_pins, sizeof(all_pins)))
    return;
  if (!testpins(9, 11, all_pins, sizeof(all_pins)))
    return;
  if (!testpins(13, PIN_SDA, all_pins, sizeof(all_pins)))
    return;
  if (!testpins(12, PIN_SCL, all_pins, sizeof(all_pins)))
    return;
  if (!testpins(AD2, AD4, all_pins, sizeof(all_pins)))
    return;
  if (!testpins(AD3, AD5, all_pins, sizeof(all_pins)))
    return;

  // test_print_adc();
  // Test 5V
  int five_mV = (float)analogRead(AD1) * 2.0 * 3.3 * 1000 / 4095.0;
  Serial_printf("5V out = %d\n\r", (int)five_mV);
  if (abs(five_mV - 5000) > 500) {
    Serial_printf("5V power supply reading wrong?");
    return;
  }
  // Accept the fixture's 9V or 12V DC supply, with measurement tolerance.
  float dc_input_volts = (float)analogRead(AD0) * 11.0f * 3.3f / 4095.0f;
  Serial_printf("DC input = %d mV\n\r", (int)(dc_input_volts * 1000.0f));
  if (dc_input_volts < DC_INPUT_MIN_VOLTS || dc_input_volts > DC_INPUT_MAX_VOLTS) {
    Serial_printf("DC input power supply reading wrong?");
    return;
  }

  if (run_sd_test) {
    if (!test_sd()) return;
  } else {
    Serial_printf("SD test skipped\r\n");
  }


  Serial_printf("*** TEST OK! ***\n\r");
}

bool testpins(uint8_t a, uint8_t b, uint8_t *allpins, uint8_t num_allpins) {
  bool ok = false;

  Serial_printf("\tTesting %d and %d\n\r", a, b);

  // set both to inputs
  pinMode(b, INPUT);
  // turn on 'a' pullup
  pinMode(a, INPUT_PULLUP);
  delay(1);

  // verify neither are grounded
  if (!digitalRead(a) || !digitalRead(b)) {
    Serial_printf("Ground test 1 fail: both pins should not be grounded");
    return false;
  }

  for (int retry = 0; retry < 3 && !ok; retry++) {
    // turn off both pullups
    pinMode(a, INPUT);
    pinMode(b, INPUT);

    // make a an output
    pinMode(a, OUTPUT);
    digitalWrite(a, LOW);
    delay(1);

    int ar = digitalRead(a);
    int br = digitalRead(b);
    delay(5);

    // make sure both are low
    if (ar || br) {
      Serial_printf("Low test fail on pin #");
      if (ar)
        Serial_printf("%d\n\r", a);
      if (br)
        Serial_printf("%d\n\r", b);
      ok = false;
      continue;
    }
    ok = true;
  }
  if (!ok)
    return false;

  ok = false;
  for (int retry = 0; retry < 3 && !ok; retry++) {
    // theSerial->println("OK!");
    // a is an input, b is an output
    pinMode(a, INPUT);
    pinMode(b, OUTPUT);
    digitalWrite(b, HIGH);
    delay(10);

    // verify neither are grounded
    if (!digitalRead(a) || !digitalRead(b)) {
      Serial_printf("Ground test 2 fail: both pins should not be grounded");
      delay(100);
      ok = false;
      continue;
    }
    ok = true;
  }
  if (!ok)
    return false;

  // make sure no pins are shorted to pin a or b
  for (uint8_t i = 0; i < num_allpins; i++) {
    pinMode(allpins[i], INPUT_PULLUP);
  }

  pinMode(a, OUTPUT);
  digitalWrite(a, LOW);
  pinMode(b, OUTPUT);
  digitalWrite(b, LOW);
  delay(1);

  for (uint8_t i = 0; i < num_allpins; i++) {
    if ((allpins[i] == a) || (allpins[i] == b)) {
      continue;
    }

    // theSerial->print("Pin #"); theSerial->print(allpins[i]);
    // theSerial->print(" -> ");
    // theSerial->println(digitalRead(allpins[i]));
    if (!digitalRead(allpins[i])) {
      Serial_printf("%d is shorted?\n\r", allpins[i]);

      return false;
    }
  }
  pinMode(a, INPUT);
  pinMode(b, INPUT);

  delay(10);

  return true;
}

void test_print_adc(void) {
  uint8_t adc_pins[] = {AD0, AD1, AD2, AD3, AD4, AD5};
  size_t const adc_pins_num = sizeof(adc_pins) / sizeof(adc_pins[0]);

  while (1) {
    printf("A0\tA1\tA2\tA3\tA4\tA5\n\r");

    for (size_t i = 0; i < adc_pins_num; i++) {
      uint16_t value = analogRead(adc_pins[i]);
      printf("%u\t", value);
    }
    printf("\r\n");

    delay(1000);
  }
}

//--------------------------------------------------------------------+
//
//--------------------------------------------------------------------+
#define LPSPI1_CLOCK_FREQ 105600000UL
#define LPSPI_MAX_FREQ 25000000UL
static const uint32_t SD_INIT_TIMEOUT_MS = 10000;
static uint32_t sd_init_started;

lpspi_master_config_t spi_config = {
    .baudRate = 400000UL,
    .bitsPerFrame = 8UL,
    .cpol = kLPSPI_ClockPolarityActiveHigh,
    .cpha = kLPSPI_ClockPhaseFirstEdge,
    .direction = kLPSPI_MsbFirst,
    .pcsToSckDelayInNanoSec = 1000,
    .lastSckToPcsDelayInNanoSec = 1000,
    .betweenTransferDelayInNanoSec = 1000,
    .whichPcs = kLPSPI_Pcs0,
    .pcsActiveHighOrLow = kLPSPI_PcsActiveLow,
    .pinCfg = kLPSPI_SdiInSdoOut,
    .dataOutConfig = kLpspiDataOutRetained
};

/*!< SPI initialization */
void sdhost_init(void){
  digitalWrite(SD_CS, HIGH);
  // we will init SPI in setFrequency
}

/*!< SPI de-initialization */
void sdhost_deinit(void){
  digitalWrite(SD_CS, HIGH);
}

/*!< SPI CS active polarity */
void sdhost_csActivePolarity(sdspi_cs_active_polarity_t polarity){
  if (polarity == kSDSPI_CsActivePolarityHigh) {
    digitalWrite(SD_CS, HIGH);
  }else {
    digitalWrite(SD_CS, LOW);
  }
}

/*!< Set frequency of SPI */
status_t sdhost_setFrequency(uint32_t frequency){
  // de-init first
  LPSPI_Deinit(LPSPI1);

  uint32_t const ns_delay = (1000000000U / frequency) * 2;
  spi_config.baudRate = frequency;
  spi_config.pcsToSckDelayInNanoSec = ns_delay;
  spi_config.lastSckToPcsDelayInNanoSec = ns_delay;
  spi_config.betweenTransferDelayInNanoSec = ns_delay;

  LPSPI_MasterInit(LPSPI1, &spi_config, LPSPI1_CLOCK_FREQ);
  // SD requires MOSI high while clocking initialization and response bytes.
  LPSPI_SetDummyData(LPSPI1, 0xFF);

  return kStatus_Success;
}

/*!< Exchange data over SPI */
status_t sdhost_exchange(uint8_t *out, uint8_t *in, uint32_t size) {
  lpspi_transfer_t xfer = {
      .txData = out,
      .rxData = in,
      .dataSize = size,
      .configFlags = kLPSPI_MasterPcsContinuous,
  };

  status_t status;

  // Keep CS asserted between the command and its separate response transfers.
  do {
    tud_task();
    tud_cdc_write_flush();
    if (millis() - sd_init_started >= SD_INIT_TIMEOUT_MS) return kStatus_Timeout;
    status = LPSPI_MasterTransferBlocking(LPSPI1, &xfer);
  } while ( status == kStatus_LPSPI_Busy );

  if ( status != kStatus_Success ) {
    printf("SPI Xfer: %ld\r\n", status);
    return status;
  }

  return kStatus_Success;
}

sdspi_host_t sdhost = {
    .busBaudRate = LPSPI_MAX_FREQ,
    .setFrequency = sdhost_setFrequency,
    .exchange = sdhost_exchange,
    .init = sdhost_init,
    .deinit = sdhost_deinit,
    .csActivePolarity = sdhost_csActivePolarity,
};

sdspi_card_t sdcard = {
    .host = &sdhost,
};

// Temporary diagnostic: print only the first three CMD0 and CMD8 replies.
static uint8_t sd_command_trace_count[2];

void sdspi_trace_command(uint8_t command, status_t status,
                         const uint8_t *response, uint8_t response_length) {
  uint8_t trace_index = command == 0 ? 0 : 1;
  uint8_t count = sd_command_trace_count[trace_index];
  if (count >= 3) return;
  sd_command_trace_count[trace_index]++;
  printf("SD CMD%u attempt %u: status %ld R1=%02X", command, count + 1,
         (long)status, response[0]);
  if (response_length == 5) {
    printf(" R7=%02X %02X %02X %02X", response[1], response[2], response[3], response[4]);
  }
  printf("\r\n");
  fflush(stdout);
  delay(1);
}

bool test_sd(void) {
  // init SD CS & Detect
  pinMode(SD_CS, OUTPUT);
  digitalWrite(SD_CS, HIGH);

  pinMode(SD_DETECT, INPUT_PULLUP);

  // init LPC SPI
  IOMUXC_SetPinMux(IOMUXC_GPIO_AD_03_LPSPI1_SDI, 0U);
  IOMUXC_SetPinMux(IOMUXC_GPIO_AD_04_LPSPI1_SDO, 0U);
  IOMUXC_SetPinMux(IOMUXC_GPIO_AD_06_LPSPI1_SCK, 0U);

  IOMUXC_SetPinConfig(IOMUXC_GPIO_AD_03_LPSPI1_SDI, 0x10A0U);
  IOMUXC_SetPinConfig(IOMUXC_GPIO_AD_04_LPSPI1_SDO, 0x10A0U);
  IOMUXC_SetPinConfig(IOMUXC_GPIO_AD_06_LPSPI1_SCK, 0x10A0U);

  if (!digitalRead(SD_DETECT)) {
    printf("SD card not inserted\r\n");
    tud_cdc_write_flush();
    return false;
  }

  printf("SD card is detected\r\n");
  fflush(stdout);
  delay(10);
  memset(sd_command_trace_count, 0, sizeof(sd_command_trace_count));
  sdcard.host = &sdhost; // SDSPI_Deinit clears the card, including this pointer.
  sd_init_started = millis();
  int status = SDSPI_Init(&sdcard);

  if (millis() - sd_init_started >= SD_INIT_TIMEOUT_MS) {
    printf("SD initialization timeout after 10000 ms\r\n");
  }
  printf("SDSPI_Init: %d\r\n", status);
  if (status == kStatus_Success) {
    uint32_t card_size_mb = sdcard.blockCount / 2 / 1024;
    printf("Card size: %lu MB\r\n", card_size_mb);
  }
  tud_cdc_write_flush();
  SDSPI_Deinit(&sdcard); // Release CS after either success or initialization failure.

  return status == kStatus_Success;
}

//--------------------------------------------------------------------+
// Logger newlib retarget
//--------------------------------------------------------------------+
#ifdef BUILD_APPLICATION
// retarget printf to usb cdc
__attribute__((used)) int _write(int fhdl, const void *buf, size_t count) {
  (void)fhdl;
  return tud_cdc_write(buf, count);
}
#endif
