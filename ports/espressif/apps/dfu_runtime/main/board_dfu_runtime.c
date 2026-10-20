/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2026 Ha Thach (tinyusb.org) for Adafruit Industries
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

#include "esp_mac.h"
#include "esp_ota_ops.h"
#include "esp_partition.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_private/system_internal.h"
#include "esp_private/usb_phy.h"
#include "esp_rom_sys.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "board_api.h"
#include "dfu_runtime.h"
#include "tusb.h"

#if BOARD_USB_FS_PHY_SWAP
#include "hal/usb_serial_jtag_ll.h"
#include "hal/usb_wrap_ll.h"
#endif

// Espressif glue for the DFU runtime example, without the bootloader's boards component

// ports/espressif/bootloader_components/main/bootloader_start.c APP_REQUEST_UF2_RESET_HINT
#define APP_REQUEST_UF2_RESET_HINT  0x11F2

extern int main(void);

static esp_timer_handle_t timer_hdl;
static usb_phy_handle_t phy_hdl;

void app_main(void) {
  main();
}

static void timer_cb(void* arg) {
  (void) arg;
  board_timer_handler();
}

void board_init(void) {
  esp_timer_create_args_t const args = { .callback = timer_cb };
  esp_timer_create(&args, &timer_hdl);
}

void board_timer_start(uint32_t ms) {
  esp_timer_stop(timer_hdl);
  esp_timer_start_periodic(timer_hdl, ms * 1000);
}

void board_timer_stop(void) {
  esp_timer_stop(timer_hdl);
}

void board_usb_init(void) {
  // same PHY setup as TinyUF2's boards.c board_dfu_init()
#if BOARD_USB_FS_PHY_SWAP
  usb_serial_jtag_ll_phy_enable_pad(false);
  vTaskDelay(pdMS_TO_TICKS(100));
#endif
  usb_phy_config_t const phy_conf = {
    .controller = USB_PHY_CTRL_OTG,
#if BOARD_TUD_RHPORT == 1 || CONFIG_IDF_TARGET_ESP32S31
    .target = USB_PHY_TARGET_UTMI, // OTG HS
#else
    .target = USB_PHY_TARGET_INT,
#endif
    .otg_mode = USB_OTG_MODE_DEVICE,
#if CONFIG_IDF_TARGET_ESP32P4 && BOARD_TUD_RHPORT == 0
    .otg_speed = USB_PHY_SPEED_FULL,
#else
    // https://github.com/hathach/tinyusb/issues/2943#issuecomment-2601888322
    .otg_speed = USB_PHY_SPEED_UNDEFINED,
#endif
  };
  ESP_ERROR_CHECK(usb_new_phy(&phy_conf, &phy_hdl));
#if BOARD_USB_FS_PHY_SWAP
  usb_wrap_ll_phy_select(&USB_WRAP, 0);
#endif
}

uint8_t board_usb_get_serial(uint8_t serial_id[16]) {
  // factory MAC, as TinyUF2 reports it
  esp_read_mac(serial_id, ESP_MAC_EFUSE_FACTORY);
  return 6;
}

void board_reboot_to_bootloader(void) {
  // the call makes the link keep esp_reset_reason_set_hint() (ports/espressif/README.md)
  (void) esp_reset_reason();
  esp_reset_reason_set_hint((esp_reset_reason_t) APP_REQUEST_UF2_RESET_HINT);
#if CONFIG_IDF_TARGET_ESP32P4 || CONFIG_IDF_TARGET_ESP32S31
  // as TinyUF2's boards.c: a software restart leaves OTG HS attached
  tud_disconnect();
  esp_rom_delay_us(20000);
#endif
  esp_restart();
}

// the HIL runner puts the nonce block in the running partition's last 256 bytes
bool board_nonce_block_read(uint8_t block[NONCE_BLOCK_SIZE]) {
  esp_partition_t const* part = esp_ota_get_running_partition();
  if (part == NULL || part->size < NONCE_BLOCK_SIZE) {
    return false;
  }
  return esp_partition_read(part, part->size - NONCE_BLOCK_SIZE, block, NONCE_BLOCK_SIZE) == ESP_OK;
}
