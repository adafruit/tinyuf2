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

#include "board_api.h"
#include "tusb.h"

// TinyUSB example IDs: 0x4000 is its product ID for a device with none of CDC, MSC, HID, MIDI or vendor
#define USB_VID   0xCafe
#define USB_PID   0x4000

extern char dfu_rt_string[];

tusb_desc_device_t const desc_device = {
  .bLength            = sizeof(tusb_desc_device_t),
  .bDescriptorType    = TUSB_DESC_DEVICE,
  .bcdUSB             = 0x0200,
  .bDeviceClass       = 0x00,
  .bDeviceSubClass    = 0x00,
  .bDeviceProtocol    = 0x00,
  .bMaxPacketSize0    = CFG_TUD_ENDPOINT0_SIZE,
  .idVendor           = USB_VID,
  .idProduct          = USB_PID,
  .bcdDevice          = 0x0100,
  .iManufacturer      = 0x01,
  .iProduct           = 0x02,
  .iSerialNumber      = 0x03,
  .bNumConfigurations = 0x01
};

uint8_t const* tud_descriptor_device_cb(void) {
  return (uint8_t const*) &desc_device;
}

enum {
  ITF_NUM_DFU_RT,
  ITF_NUM_TOTAL
};

#define CONFIG_TOTAL_LEN  (TUD_CONFIG_DESC_LEN + TUD_DFU_RT_DESC_LEN)

// attributes 0x0d: bitWillDetach, bitManifestationTolerant, bitCanDnload; with bitWillDetach the device
// leaves the bus itself after DETACH and the host issues no USB reset
uint8_t const desc_configuration[] = {
  TUD_CONFIG_DESCRIPTOR(1, ITF_NUM_TOTAL, 0, CONFIG_TOTAL_LEN, 0x00, 100),
  TUD_DFU_RT_DESCRIPTOR(ITF_NUM_DFU_RT, 4, 0x0d, 1000, 4096),
};

uint8_t const* tud_descriptor_configuration_cb(uint8_t index) {
  (void) index;
  return desc_configuration;
}

enum {
  STRID_LANGID = 0,
  STRID_MANUFACTURER,
  STRID_PRODUCT,
  STRID_SERIAL,
  STRID_DFU_RT,
};

static uint16_t _desc_str[48 + 1];

uint16_t const* tud_descriptor_string_cb(uint8_t index, uint16_t langid) {
  (void) langid;
  char const* str;
  uint8_t chr_count;

  switch (index) {
    case STRID_LANGID:
      _desc_str[1] = 0x0409;
      chr_count = 1;
      break;

    // same format as TinyUF2's serial, so the app and the bootloader report one identity
    case STRID_SERIAL: {
      uint8_t serial_id[16] TU_ATTR_ALIGNED(4);
      uint8_t serial_len = board_usb_get_serial(serial_id);
      static const char hex[] = "0123456789ABCDEF";
      chr_count = 2 * serial_len;
      for (uint8_t i = 0; i < serial_len; i++) {
        _desc_str[1 + 2 * i] = hex[serial_id[i] >> 4];
        _desc_str[2 + 2 * i] = hex[serial_id[i] & 0xf];
      }
      break;
    }

    default:
      switch (index) {
        case STRID_MANUFACTURER: str = "TinyUF2"; break;
        case STRID_PRODUCT: str = "TinyUF2 DFU runtime example"; break;
        case STRID_DFU_RT: str = dfu_rt_string; break;
        default: return NULL;
      }
      chr_count = (uint8_t) TU_MIN(strlen(str), TU_ARRAY_SIZE(_desc_str) - 1);
      for (uint8_t i = 0; i < chr_count; i++) {
        _desc_str[1 + i] = str[i];
      }
      break;
  }

  _desc_str[0] = (uint16_t) ((TUSB_DESC_STRING << 8) | (2 * chr_count + 2));
  return _desc_str;
}
