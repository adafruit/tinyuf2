// SPDX-FileCopyrightText: Copyright (c) 2019 ladyada for Adafruit Industries
// SPDX-License-Identifier: MIT
// NINA framing and handshake follow Adafruit_CircuitPython_ESP32SPI.
// Pin assignments follow CircuitPython's metro_m7_1011 board definition.
#include "arduino.h"
#include "wifi_scan.h"

#define ESP_CS_PIN 28
#define ESP_BUSY_PIN 25
#define SPI_MISO_PIN 17
#define SPI_MOSI_PIN 18
#define SPI_SCK_PIN 20
#define SCAN_BUDGET_MS 20000U
#define MAX_SSIDS 64
#define MAX_SSID_LENGTH 32

static uint32_t scan_start;
static bool timed_out;
static unsigned service_bytes;
static uint8_t names[MAX_SSIDS][MAX_SSID_LENGTH];
static uint8_t lengths[MAX_SSIDS];

static bool within_budget(void) {
  demo_service();
  if (millis() - scan_start >= SCAN_BUDGET_MS) {
    timed_out = true;
  }
  return !timed_out;
}

static bool pause_ms(uint32_t ms) {
  uint32_t start = millis();
  while (millis() - start < ms) {
    if (!within_budget()) {
      return false;
    }
  }
  return within_budget();
}

static void deselect(void) {
  GPIO_PinWrite(GPIO1, ESP_CS_PIN, 1);
}

static bool select_esp(void) {
  while (GPIO_PinRead(GPIO1, ESP_BUSY_PIN)) {
    if (!within_budget()) {
      return false;
    }
  }
  GPIO_PinWrite(GPIO1, ESP_CS_PIN, 0);
  uint32_t start = millis();
  while (!GPIO_PinRead(GPIO1, ESP_BUSY_PIN)) {
    if (!within_budget() || millis() - start >= 1000) {
      deselect();
      return false;
    }
  }
  return within_budget();
}

// Mode 0, MSB first. Delay each half cycle; actual clock is below 500 kHz.
static uint8_t exchange(uint8_t value) {
  if ((service_bytes++ & 15U) == 0 && !within_budget()) {
    return 0xff;
  }
  uint8_t reply = 0;
  for (unsigned bit = 0; bit < 8; bit++) {
    GPIO_PinWrite(GPIO1, SPI_MOSI_PIN, (value & 0x80) != 0);
    value <<= 1;
    SDK_DelayAtLeastUs(1, SystemCoreClock);
    GPIO_PinWrite(GPIO1, SPI_SCK_PIN, 1);
    SDK_DelayAtLeastUs(1, SystemCoreClock);
    reply = (uint8_t)((reply << 1) | GPIO_PinRead(GPIO1, SPI_MISO_PIN));
    GPIO_PinWrite(GPIO1, SPI_SCK_PIN, 0);
  }
  return reply;
}

static bool send_command(uint8_t command) {
  if (!select_esp()) {
    return false;
  }
  exchange(0xe0);
  exchange(command);
  exchange(0);
  exchange(0xee);
  deselect();
  return within_budget();
}

static bool read_response(uint8_t command, uint8_t *count) {
  if (!select_esp()) {
    return false;
  }
  bool started = false;
  for (unsigned attempt = 0; attempt < 10; attempt++) {
    uint8_t byte = exchange(0xff);
    if (byte == 0xe0) {
      started = true;
      break;
    }
    if (byte == 0xef || !pause_ms(10)) {
      break;
    }
  }
  if (!started || exchange(0xff) != (command | 0x80)) {
    deselect();
    return false;
  }
  *count = exchange(0xff);
  if (*count > MAX_SSIDS || (command != 0x27 && *count != 1)) {
    deselect();
    return false;
  }
  for (unsigned i = 0; i < *count; i++) {
    lengths[i] = exchange(0xff);
    if (lengths[i] > MAX_SSID_LENGTH) {
      deselect();
      return false;
    }
    for (unsigned j = 0; j < lengths[i]; j++) {
      names[i][j] = exchange(0xff);
    }
  }
  bool valid = exchange(0xff) == 0xee && !timed_out;
  deselect();
  return valid && within_budget();
}

static bool command_response(uint8_t command, uint8_t *count) {
  return send_command(command) && read_response(command, count);
}

// No control characters from radio data may affect the fixture's result parser.
static void print_escaped(const uint8_t *data, unsigned length) {
  static const char hex[] = "0123456789ABCDEF";
  char escaped[MAX_SSID_LENGTH * 4 + 1];
  unsigned out = 0;
  for (unsigned i = 0; i < length; i++) {
    uint8_t byte = data[i];
    if (byte >= 0x20 && byte <= 0x7e && byte != '\\') {
      escaped[out++] = (char)byte;
    } else {
      escaped[out++] = '\\';
      escaped[out++] = 'x';
      escaped[out++] = hex[byte >> 4];
      escaped[out++] = hex[byte & 15];
    }
  }
  escaped[out] = 0;
  printf("%s\n", escaped);
  fflush(stdout);
  demo_service();
}

static bool has_name(unsigned index) {
  for (unsigned i = 0; i < lengths[index]; i++) {
    uint8_t byte = names[index][i];
    if (byte >= 0x20 && byte != 0x7f) {
      return true;
    }
  }
  return false;
}

static bool init_esp(void) {
  gpio_pin_config_t output_high = {kGPIO_DigitalOutput, 1, kGPIO_NoIntmode};
  gpio_pin_config_t output_low = {kGPIO_DigitalOutput, 0, kGPIO_NoIntmode};
  gpio_pin_config_t input = {kGPIO_DigitalInput, 0, kGPIO_NoIntmode};
  GPIO_PinInit(GPIO1, ESP_CS_PIN, &output_high);
  IOMUXC_SetPinConfig(IOMUXC_GPIO_AD_14_GPIOMUX_IO28, 0x00B0U);
  IOMUXC_SetPinMux(IOMUXC_GPIO_AD_14_GPIOMUX_IO28, 0);
  GPIO_PinInit(GPIO1, ESP_BUSY_PIN, &input);
  IOMUXC_SetPinConfig(IOMUXC_GPIO_AD_11_GPIOMUX_IO25, 0x00B0U);
  IOMUXC_SetPinMux(IOMUXC_GPIO_AD_11_GPIOMUX_IO25, 0);
  GPIO_PinInit(GPIO1, SPI_MISO_PIN, &input);
  IOMUXC_SetPinConfig(IOMUXC_GPIO_AD_03_GPIOMUX_IO17, 0x00B0U);
  IOMUXC_SetPinMux(IOMUXC_GPIO_AD_03_GPIOMUX_IO17, 0);
  GPIO_PinInit(GPIO1, SPI_MOSI_PIN, &output_low);
  IOMUXC_SetPinConfig(IOMUXC_GPIO_AD_04_GPIOMUX_IO18, 0x00B0U);
  IOMUXC_SetPinMux(IOMUXC_GPIO_AD_04_GPIOMUX_IO18, 0);
  GPIO_PinInit(GPIO1, SPI_SCK_PIN, &output_low);
  IOMUXC_SetPinConfig(IOMUXC_GPIO_AD_06_GPIOMUX_IO20, 0x00B0U);
  IOMUXC_SetPinMux(IOMUXC_GPIO_AD_06_GPIOMUX_IO20, 0);
  GPIO_PinInit(ESP32_GPIO0_PORT, ESP32_GPIO0_PIN, &output_high);
  IOMUXC_SetPinConfig(ESP32_GPIO0_PINMUX, 0x00B0U);
  IOMUXC_SetPinMux(ESP32_GPIO0_PINMUX, 0);
  GPIO_PinInit(ESP32_RESET_PORT, ESP32_RESET_PIN, &output_low);
  IOMUXC_SetPinConfig(ESP32_RESET_PINMUX, 0x00B0U);
  IOMUXC_SetPinMux(ESP32_RESET_PINMUX, 0);
  bool ready = pause_ms(10);
  GPIO_PinWrite(ESP32_RESET_PORT, ESP32_RESET_PIN, 1);
  ready = ready && pause_ms(750);
  GPIO_PinInit(ESP32_GPIO0_PORT, ESP32_GPIO0_PIN, &input);
  return ready;
}

int wifi_scan(void) {
  scan_start = millis();
  timed_out = false;
  service_bytes = 0;
  uint8_t count;
  if (!init_esp() || !command_response(0x37, &count) || !lengths[0]) {
    printf("WiFi FAILED: firmware response or timeout\n");
    goto fail;
  }
  printf("WiFi firmware: ");
  print_escaped(names[0], lengths[0]);
  if (!command_response(0x36, &count) || lengths[0] != 1 || names[0][0] != 1) {
    printf("WiFi FAILED: start scan response or timeout\n");
    goto fail;
  }
  // Leave time for the radio scan; all waits share the same absolute deadline.
  while (millis() - scan_start < SCAN_BUDGET_MS - 2000U) {
    if (!pause_ms(2000) || !command_response(0x27, &count)) {
      printf("WiFi FAILED: scan response or timeout\n");
      goto fail;
    }
    int valid = 0;
    for (unsigned i = 0; i < count; i++) {
      if (has_name(i)) {
        printf("SSID: ");
        print_escaped(names[i], lengths[i]);
        valid++;
      }
    }
    if (valid) {
      return valid;
    }
  }
  printf("WiFi FAILED: no visible SSIDs\n");
  fflush(stdout);
  demo_service();
  return 0;

fail:
  deselect();
  fflush(stdout);
  demo_service();
  return -1;
}
