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

#include "arduino.h"
#include "board_api.h"
#include "tusb.h"

void loop(void);

uint8_t all_pins[] = {0,       1,       2,        3,        4,       5,  6,
                      7,       8,       9,        10,       11,      12, 13,
                      PIN_SDA, PIN_SCL, PIN_MOSI, PIN_MISO, PIN_SCK, AD5};

bool test = false;

bool testpins(uint8_t a, uint8_t b, uint8_t *allpins, uint8_t num_allpins);
void test_print_adc(void);

/* This is an application to test Metro M7
 */

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

  // wait for Serial connection
  if (test) {
    while (!tud_cdc_connected()) {
      tud_task();
    }
  }

  while (1) {
    loop();
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
    if (count && serial_buf[0] == 0xAF) {
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
  if (!testpins(PIN_MOSI, PIN_MISO, all_pins, sizeof(all_pins)))
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
  // Test 5V
  int nine_mV = (float)analogRead(AD0) * 11.0 * 3.3 * 1000 / 4095.0;
  Serial_printf("9V out = %d\n\r", (int)nine_mV);
  if (abs(nine_mV - 9000) > 1000) {
    Serial_printf("9V power supply reading wrong?");
    return;
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
// Logger newlib retarget
//--------------------------------------------------------------------+

// retarget printf to usb cdc
__attribute__((used)) int _write(int fhdl, const void *buf, size_t count) {
  (void)fhdl;
  return tud_cdc_write(buf, count);
}
