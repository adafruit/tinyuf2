/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2019 Ha Thach (tinyusb.org)
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
 *
 */

#include "board_api.h"
#include "tusb.h"

// Interface number
enum {
#if CFG_TUD_CDC
  ITF_NUM_CDC,
  ITF_NUM_CDC_DATA,
#endif
  ITF_NUM_MSC,
  ITF_NUM_TOTAL
};

// String Descriptor Index
enum {
  STRID_LANGID = 0,
  STRID_MANUFACTURER,
  STRID_PRODUCT,
  STRID_SERIAL,
#if CFG_TUD_CDC
  STRID_CDC,
  STRID_CDC_DATA,
#endif
  STRID_MSC,
};

//--------------------------------------------------------------------+
// Device Descriptors
//--------------------------------------------------------------------+
tusb_desc_device_t TINYUF2_CONST desc_device = {
    .bLength            = sizeof(tusb_desc_device_t),
    .bDescriptorType    = TUSB_DESC_DEVICE,
    .bcdUSB             = 0x0200,
#if CFG_TUD_CDC
    // Use Interface Association Descriptor (IAD) for CDC
    .bDeviceClass       = TUSB_CLASS_MISC,
    .bDeviceSubClass    = MISC_SUBCLASS_COMMON,
    .bDeviceProtocol    = MISC_PROTOCOL_IAD,
#else
    .bDeviceClass       = 0x00,
    .bDeviceSubClass    = 0x00,
    .bDeviceProtocol    = 0x00,
#endif
    .bMaxPacketSize0    = CFG_TUD_ENDPOINT0_SIZE,
    .idVendor           = USB_VID,
    .idProduct          = USB_PID,
    .bcdDevice          = 0x0101,
    .iManufacturer      = STRID_MANUFACTURER,
    .iProduct           = STRID_PRODUCT,
    .iSerialNumber      = STRID_SERIAL,
    .bNumConfigurations = 0x01
};

// Invoked when received GET DEVICE DESCRIPTOR
// Application return pointer to descriptor
uint8_t const* tud_descriptor_device_cb(void) {
  return (uint8_t const*) &desc_device;
}

//--------------------------------------------------------------------+
// Configuration Descriptor
//--------------------------------------------------------------------+

#define CONFIG_TOTAL_LEN  (TUD_CONFIG_DESC_LEN + TUD_MSC_DESC_LEN + \
                           CFG_TUD_CDC*TUD_CDC_DESC_LEN + CFG_TUD_VENDOR*TUD_VENDOR_DESC_LEN)

// MSC is mandatory, use endpoint 1
#define EPNUM_MSC_OUT     0x01
#define EPNUM_MSC_IN      0x81

// Board/Port can force CDC endpoint numbering
#if defined(BOARD_EPNUM_CDC_OUT) && defined(BOARD_EPNUM_CDC_IN) && defined(BOARD_EPNUM_CDC_NOTIF)
  #define EPNUM_CDC_NOTIF   BOARD_EPNUM_CDC_NOTIF
  #define EPNUM_CDC_OUT     BOARD_EPNUM_CDC_OUT
  #define EPNUM_CDC_IN      BOARD_EPNUM_CDC_IN
#else
  #define EPNUM_CDC_NOTIF   0x82
  #define EPNUM_CDC_OUT     0x03
  #define EPNUM_CDC_IN      0x83
#endif

uint8_t TINYUF2_CONST desc_configuration[] = {
    // Config number, interface count, string index, total length, attribute, power in mA
    TUD_CONFIG_DESCRIPTOR(1, ITF_NUM_TOTAL, 0, CONFIG_TOTAL_LEN, TUSB_DESC_CONFIG_ATT_REMOTE_WAKEUP, 100),
#if CFG_TUD_CDC
    // Interface number, string index, EP notification address and size, EP data address (out, in) and size.
    TUD_CDC_DESCRIPTOR(ITF_NUM_CDC, STRID_CDC, EPNUM_CDC_NOTIF, 8, EPNUM_CDC_OUT, EPNUM_CDC_IN, TUD_OPT_HIGH_SPEED ? 512 : 64),
#endif
    // Interface number, string index, EP Out & EP In address, EP size
    TUD_MSC_DESCRIPTOR(ITF_NUM_MSC, STRID_MSC, EPNUM_MSC_OUT, EPNUM_MSC_IN, TUD_OPT_HIGH_SPEED ? 512 : 64),
};


// Invoked when received GET CONFIGURATION DESCRIPTOR
// Application return pointer to descriptor
// Descriptor contents must exist long enough for transfer to complete
uint8_t const* tud_descriptor_configuration_cb(uint8_t index) {
  (void) index; // for multiple configurations

  // TODO when device is highspeed, host is fullspeed.
  return desc_configuration;
}

//--------------------------------------------------------------------+
// String Descriptors
//--------------------------------------------------------------------+

// Serial is 64-bit DeviceID -> 16 chars len
static char desc_str_serial[1 + 16] = { 0 };

// array of pointer to string descriptors
char const* string_desc_arr[] = {
    (const char[]) { 0x09, 0x04 }, // 0: is supported language is English (0x0409)
    USB_MANUFACTURER,              // 1: Manufacturer
    USB_PRODUCT,                   // 2: Product
    desc_str_serial,               // 3: Serials, use default MAC address
#if CFG_TUD_CDC
    "TinyUF2 CDC",                 // 4: CDC Interface
    NULL,
#endif
    "UF2",                         // 4: MSC Interface
};

static uint16_t _desc_str[48 + 1];

// Invoked when received GET STRING DESCRIPTOR request
// Application return pointer to descriptor, whose contents must exist long enough for transfer to complete
uint16_t const* tud_descriptor_string_cb(uint8_t index, uint16_t langid) {
  (void) langid;
  uint8_t chr_count;

  switch (index) {
    case STRID_LANGID:
      memcpy(&_desc_str[1], string_desc_arr[0], 2);
      chr_count = 1;
      break;

    // TODO light alternation such as +1 to prevent conflict with application
    case STRID_SERIAL: {
      uint8_t serial_id[16] TU_ATTR_ALIGNED(4);
      uint8_t serial_len = board_usb_get_serial(serial_id);
      chr_count = 2 * serial_len;

      for (uint8_t i = 0; i < serial_len; i++) {
        for (uint8_t j = 0; j < 2; j++) {
          const char nibble_to_hex[16] = {
              '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F'
          };
          uint8_t nibble = (serial_id[i] >> (j * 4)) & 0xf;
          _desc_str[1 + i * 2 + (1 - j)] = nibble_to_hex[nibble]; // UTF-16-LE
        }
      }
      break;
    }

    default: {
      // Convert ASCII string into UTF-16
      if (!(index < sizeof(string_desc_arr) / sizeof(string_desc_arr[0]))) return NULL;

      uint16_t const max_count = (sizeof(_desc_str) / sizeof(_desc_str[0])) - 1;

      const char* str = string_desc_arr[index];
      chr_count = strlen(str);

      // Cap at max char
      if (chr_count > max_count) chr_count = max_count;

      for (uint8_t i = 0; i < chr_count; i++) {
        _desc_str[1 + i] = str[i];
      }
      break;
    }
  }

  // first byte is length (including header), second byte is string type
  _desc_str[0] = (TUSB_DESC_STRING << 8) | (2 * chr_count + 2);

  return _desc_str;
}
