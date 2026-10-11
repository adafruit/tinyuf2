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
#include "wifi_scan.h"

void loop(void);

uint8_t all_pins[] = {0,       1,       2,        3,        4,       5,  6,
                      7,       8,       9,        10,       11,      12, 13,
                      PIN_SDA, PIN_SCL, PIN_MOSI, PIN_MISO, PIN_SCK, AD5};

bool test = false;
static const float DC_INPUT_MIN_VOLTS = 8.0f;
static const float DC_INPUT_MAX_VOLTS = 13.0f;

bool testpins(uint8_t a, uint8_t b, uint8_t *allpins, uint8_t num_allpins);
void test_print_adc(void);
static bool test_board(void);
static uint32_t next_scan = 5000;
static bool serial_connected = false;

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
    // Failure messages may have no newline; drain libc before the USB FIFO.
    fflush(stdout);
    tud_task();
    tud_cdc_write_flush();
  }
}

void demo_service(void) {
  static uint32_t last_animation = 0;
  static uint8_t color = 0;
  uint32_t now = millis();
  if (now - last_animation >= 20) {
    last_animation = now;
    setColor(neoWheel(color++));
    digitalWrite(13, (now % 1000) < 500);
  }
  fflush(stdout);
  tud_task();
  tud_cdc_write_flush();
}

void loop(void) {
  bool connected = tud_cdc_connected();
  if (connected && !serial_connected) {
    Serial_printf("\r\nHello from your Metro M7 AirLift!\r\n");
    Serial_printf("Watch the red LED blink and the NeoPixel swirl.\r\n");
    Serial_printf("Nearby Wi-Fi networks are listed every 30 seconds.\r\n");
    next_scan = millis() + 5000;
  }
  serial_connected = connected;
  if (tud_cdc_available()) {
    uint8_t serial_buf[256];
    uint32_t count;

    count = tud_cdc_read(serial_buf, sizeof(serial_buf));
    if (count && serial_buf[0] == 0xAF) {
      test = true;
    }
  }

  if (!test) {
    demo_service();
    if ((int32_t)(millis() - next_scan) >= 0) {
      Serial_printf("\r\nScanning nearby Wi-Fi networks...\r\n");
      int networks = wifi_scan();
      if (networks == 0) Serial_printf("No named networks found. Trying again in 30 seconds.\r\n");
      next_scan = millis() + 30000;
    }
    return;
  }

  test = false; // Run one pass per start command, including failed passes.

  // Keep the ESP32 from driving the UART and SPI loopback pins during testing.
  gpio_pin_config_t reset_config = {kGPIO_DigitalOutput, 0, kGPIO_NoIntmode};
  IOMUXC_SetPinMux(ESP32_RESET_PINMUX, 0);
  IOMUXC_SetPinConfig(ESP32_RESET_PINMUX, 0x10B0U);
  GPIO_PinInit(ESP32_RESET_PORT, ESP32_RESET_PIN, &reset_config);
  delay(100);
  bool gpio_passed = test_board();

  // Release every tested output before allowing the ESP32 to run, even on failure.
  for (size_t i = 0; i < sizeof(all_pins); i++) {
    pinMode(all_pins[i], INPUT);
  }
  for (uint8_t pin = AD0; pin <= AD5; pin++) {
    pinMode(pin, INPUT);
  }
  GPIO_PinWrite(ESP32_RESET_PORT, ESP32_RESET_PIN, 1);
  pinMode(13, OUTPUT);
  if (gpio_passed) {
    Serial_printf("WiFi scan required for factory pass...\r\n");
    int networks = wifi_scan();
    if (networks > 0) {
      Serial_printf("WIFI SCAN OK\r\n");
      Serial_printf("*** TEST OK! ***\r\n");
    } else {
      Serial_printf("WiFi FAILED: no valid SSIDs detected.\r\n");
    }
  }
  next_scan = millis() + 30000;
}

static bool test_board(void) {
  Serial_printf("\n\r\n\rHello Metro M7 iMX RT1011 Test! %lu\n\r", millis());

  if (!testpins(0, 2, all_pins, sizeof(all_pins)))
    return false;
  if (!testpins(1, 3, all_pins, sizeof(all_pins)))
    return false;
  if (!testpins(4, 6, all_pins, sizeof(all_pins)))
    return false;
  if (!testpins(5, 7, all_pins, sizeof(all_pins)))
    return false;
  if (!testpins(8, 10, all_pins, sizeof(all_pins)))
    return false;
  if (!testpins(9, 11, all_pins, sizeof(all_pins)))
    return false;
  if (!testpins(13, PIN_SDA, all_pins, sizeof(all_pins)))
    return false;
  if (!testpins(12, PIN_SCL, all_pins, sizeof(all_pins)))
    return false;
  // The SPI loopback is not connected in the Brains fixture.
  if (!testpins(AD2, AD4, all_pins, sizeof(all_pins)))
    return false;
  if (!testpins(AD3, AD5, all_pins, sizeof(all_pins)))
    return false;

  // test_print_adc();
  // Test 5V
  int five_mV = (float)analogRead(AD1) * 2.0 * 3.3 * 1000 / 4095.0;
  Serial_printf("5V out = %d\n\r", (int)five_mV);
  if (abs(five_mV - 5000) > 500) {
    Serial_printf("5V power supply reading wrong?");
    return false;
  }
  // Accept the fixture's 9V or 12V DC supply, with measurement tolerance.
  float dc_input_volts = (float)analogRead(AD0) * 11.0f * 3.3f / 4095.0f;
  Serial_printf("DC input = %d mV\n\r", (int)(dc_input_volts * 1000.0f));
  if (dc_input_volts < DC_INPUT_MIN_VOLTS || dc_input_volts > DC_INPUT_MAX_VOLTS) {
    Serial_printf("DC input power supply reading wrong?");
    return false;
  }
  return true;
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
  if (!tud_cdc_connected()) return (int)count;
  const uint8_t *bytes = buf;
  size_t written = 0;
  uint32_t started = millis();
  while (written < count && tud_cdc_connected() && millis() - started < 1000) {
    written += tud_cdc_write(bytes + written, count - written);
    tud_cdc_write_flush();
    tud_task();
  }
  return (int)written;
}
