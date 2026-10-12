// SPDX-FileCopyrightText: Copyright (c) 2019 ladyada for Adafruit Industries
// SPDX-License-Identifier: MIT
// NINA framing and handshake follow Adafruit_CircuitPython_ESP32SPI.
// Pin assignments follow CircuitPython's metro_m7_1011 board definition.
#include "arduino.h"
#include "wifi_scan.h"
#include "fsl_lpspi.h"

#define ESP_CS_PIN 28
#define ESP_BUSY_PIN 25
#define SCAN_BUDGET_MS 20000U
#define MAX_SSIDS 64
#define MAX_SSID_LENGTH 32

static uint32_t scan_start;
static bool timed_out;
static unsigned service_bytes;
static lpspi_master_handle_t spi_handle;
static volatile bool spi_done;
static volatile status_t spi_status;
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

static bool spi_error(const char *stage, unsigned value) {
  deselect();
  printf("WiFi SPI detail: %s (%02X)\n\r", stage, value);
  fflush(stdout);
  demo_service();
  return false;
}

static bool select_esp(void) {
  while (GPIO_PinRead(GPIO1, ESP_BUSY_PIN)) {
    if (!within_budget()) {
      return spi_error("BUSY stayed high before CS", 1);
    }
  }
  GPIO_PinWrite(GPIO1, ESP_CS_PIN, 0);
  uint32_t start = millis();
  while (!GPIO_PinRead(GPIO1, ESP_BUSY_PIN)) {
    if (!within_budget() || millis() - start >= 1000) {
      return spi_error("BUSY stayed low after CS", 0);
    }
  }
  if (!within_budget()) {
    return spi_error("deadline after CS", 0);
  }
  return true;
}

static void spi_complete(LPSPI_Type *base, lpspi_master_handle_t *handle,
                         status_t status, void *user_data) {
  (void)base;
  (void)handle;
  (void)user_data;
  spi_status = status;
  spi_done = true;
}

// Hardware mode-0 sampling avoids the ESP32 DMA MISO hold-time limitation.
static bool transfer_bytes(uint8_t *data, size_t length, uint8_t *reply) {
  if (timed_out || ((service_bytes++ & 15U) == 0 && !within_budget())) {
    return false;
  }
  lpspi_transfer_t transfer = {
      .txData = data,
      .rxData = reply,
      .dataSize = length,
      .configFlags = kLPSPI_MasterPcsContinuous,
  };
  spi_done = false;
  status_t status = LPSPI_MasterTransferNonBlocking(LPSPI1, &spi_handle, &transfer);
  if (status == kStatus_Success) {
    while (!spi_done) {
      if (!within_budget()) {
        LPSPI_MasterTransferAbort(LPSPI1, &spi_handle);
        return spi_error("LPSPI deadline", 0);
      }
    }
    status = spi_status;
  }
  if (status != kStatus_Success) {
    timed_out = true;
    return spi_error("LPSPI transfer", status);
  }
  return true;
}

static uint8_t exchange(uint8_t value) {
  uint8_t reply = 0xff;
  transfer_bytes(&value, 1, &reply);
  return reply;
}

static bool send_command(uint8_t command) {
  if (!select_esp()) {
    return false;
  }
  uint8_t packet[] = {0xe0, command, 0, 0xee};
  bool sent = transfer_bytes(packet, sizeof(packet), NULL);
  deselect();
  return sent && within_budget();
}

static bool read_response(uint8_t command, uint8_t *count) {
  if (!select_esp()) {
    return false;
  }
  bool started = false;
  uint8_t byte = 0xff;
  for (unsigned attempt = 0; attempt < 10; attempt++) {
    byte = exchange(0xff);
    if (byte == 0xe0) {
      started = true;
      break;
    }
    if (byte == 0xef || !pause_ms(10)) {
      break;
    }
  }
  if (!started) {
    return spi_error("response start byte", byte);
  }
  byte = exchange(0xff);
  if (byte != (command | 0x80)) {
    return spi_error("reply command", byte);
  }
  *count = exchange(0xff);
  if (*count > MAX_SSIDS || (command != 0x27 && *count != 1)) {
    return spi_error("parameter count", *count);
  }
  for (unsigned i = 0; i < *count; i++) {
    lengths[i] = exchange(0xff);
    if (lengths[i] > MAX_SSID_LENGTH) {
      return spi_error("parameter length", lengths[i]);
    }
    for (unsigned j = 0; j < lengths[i]; j++) {
      names[i][j] = exchange(0xff);
    }
  }
  byte = exchange(0xff);
  if (byte != 0xee) {
    return spi_error("response end byte", byte);
  }
  deselect();
  return within_budget();
}

static bool command_response(uint8_t command, uint8_t *count) {
  return send_command(command) && read_response(command, count);
}

// Indexed NINA commands each contain one one-byte network-index parameter.
static bool network_detail(uint8_t command, uint8_t index, uint8_t length) {
  if (!select_esp()) {
    return false;
  }
  uint8_t packet[] = {0xe0, command, 1, 1, index, 0xee, 0xff, 0xff};
  bool sent = transfer_bytes(packet, sizeof(packet), NULL);
  deselect();
  uint8_t count;
  return sent && read_response(command, &count) && lengths[0] == length;
}

// NINA 3.3.0 returns ESP-IDF 5.5 wifi_auth_mode_t for indexed scan results.
// This differs from the legacy NINA current-network encryption codes.
// https://github.com/espressif/esp-idf/blob/v5.5/components/esp_wifi/include/esp_wifi_types_generic.h
static const char *encryption_name(uint8_t mode) {
  switch (mode) {
    case 0: return "OPEN";
    case 1: return "WEP";
    case 2: return "WPA-PSK";
    case 3: return "WPA2-PSK";
    case 4: return "WPA/WPA2-PSK";
    case 5: return "WPA2-Enterprise";
    case 6: return "WPA3-PSK";
    case 7: return "WPA2/WPA3-PSK";
    case 8: return "WAPI-PSK";
    case 9: return "OWE";
    case 10: return "WPA3-Enterprise-192";
    case 11: return "WPA3-PSK";
    case 12: return "WPA3-PSK";
    case 13: return "DPP";
    case 14: return "WPA3-Enterprise";
    case 15: return "WPA2/WPA3-Enterprise";
    case 16: return "WPA-Enterprise";
    default: return "UNKNOWN";
  }
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
  printf("%s", escaped);
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
  IOMUXC_SetPinMux(IOMUXC_GPIO_AD_14_GPIOMUX_IO28, 1);
  GPIO_PinInit(GPIO1, ESP_BUSY_PIN, &input);
  IOMUXC_SetPinConfig(IOMUXC_GPIO_AD_11_GPIOMUX_IO25, 0x00B0U);
  IOMUXC_SetPinMux(IOMUXC_GPIO_AD_11_GPIOMUX_IO25, 0);
  // Use the same LPSPI1 routing and pad settings as the Metro microSD test.
  IOMUXC_SetPinMux(IOMUXC_GPIO_AD_03_LPSPI1_SDI, 1);
  IOMUXC_SetPinMux(IOMUXC_GPIO_AD_04_LPSPI1_SDO, 0);
  IOMUXC_SetPinMux(IOMUXC_GPIO_AD_06_LPSPI1_SCK, 0);
  IOMUXC_SetPinConfig(IOMUXC_GPIO_AD_03_LPSPI1_SDI, 0x10A0U);
  IOMUXC_SetPinConfig(IOMUXC_GPIO_AD_04_LPSPI1_SDO, 0x10A0U);
  IOMUXC_SetPinConfig(IOMUXC_GPIO_AD_06_LPSPI1_SCK, 0x10A0U);
  lpspi_master_config_t spi_config;
  LPSPI_MasterGetDefaultConfig(&spi_config);
  spi_config.baudRate = 1000000;
  spi_config.bitsPerFrame = 8;
  spi_config.cpol = kLPSPI_ClockPolarityActiveHigh;
  spi_config.cpha = kLPSPI_ClockPhaseFirstEdge;
  spi_config.direction = kLPSPI_MsbFirst;
  // BOARD_BootClockRUN selects the 528 MHz system PLL divided by five.
  // Keep this source frequency consistent with the validated microSD test.
  const uint32_t lpspi_source_clock_hz = 105600000UL;
  LPSPI_MasterInit(LPSPI1, &spi_config, lpspi_source_clock_hz);
  LPSPI_MasterTransferCreateHandle(LPSPI1, &spi_handle, spi_complete, NULL);
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
  if (!init_esp()) {
    printf("WiFi FAILED: initialization or timeout\n\r");
    goto fail;
  }
  bool firmware_ok = command_response(0x37, &count);
  if (!firmware_ok || !lengths[0]) {
    printf("WiFi FAILED: firmware response or timeout\n\r");
    goto fail;
  }
  printf("WiFi firmware: ");
  unsigned version_length = lengths[0];
  if (names[0][version_length - 1] == 0) {
    version_length--;
  }
  print_escaped(names[0], version_length);
  printf("\n\r");
  if (!command_response(0x36, &count) || lengths[0] != 1 || names[0][0] != 1) {
    printf("WiFi FAILED: start scan response or timeout\n\r");
    goto fail;
  }
  // Leave time for the radio scan; all waits share the same absolute deadline.
  while (millis() - scan_start < SCAN_BUDGET_MS - 2000U) {
    if (!pause_ms(2000) || !command_response(0x27, &count)) {
      printf("WiFi FAILED: scan response or timeout\n\r");
      goto fail;
    }
    int valid = 0;
    for (unsigned i = 0; i < count; i++) {
      if (has_name(i)) {
        // Detail responses reuse slot zero; save this SSID before querying.
        uint8_t name[MAX_SSID_LENGTH];
        uint8_t name_length = lengths[i];
        memcpy(name, names[i], name_length);
        if (!network_detail(0x32, i, sizeof(int32_t))) {
          printf("WiFi FAILED: RSSI response or timeout\n\r");
          goto fail;
        }
        // NINA and this M7 both encode int32_t as little-endian.
        int32_t rssi;
        memcpy(&rssi, names[0], sizeof(rssi));
        if (!network_detail(0x33, i, 1)) {
          printf("WiFi FAILED: encryption response or timeout\n\r");
          goto fail;
        }
        uint8_t encryption = names[0][0];
        printf("SSID: ");
        print_escaped(name, name_length);
        printf(" | %ld dBm | %s (%u)\n\r", (long)rssi,
               encryption_name(encryption), encryption);
        fflush(stdout);
        demo_service();
        valid++;
      }
    }
    if (valid) {
      return valid;
    }
  }
  printf("WiFi FAILED: no visible SSIDs\n\r");
  fflush(stdout);
  demo_service();
  return 0;

fail:
  deselect();
  fflush(stdout);
  demo_service();
  return -1;
}
