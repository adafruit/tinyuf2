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

// String Descriptor Index
enum
{
  STRID_LANGID = 0,
  STRID_MANUFACTURER,
  STRID_PRODUCT,
  STRID_SERIAL,
  STRID_MSC,
  STRID_HID,
  STRID_VENDOR,
};

enum
{
  ITF_NUM_MSC,
  ITF_NUM_HID,

#if CFG_TUD_VENDOR
  ITF_NUM_VENDOR, // webUSB
#endif

  ITF_NUM_TOTAL
};

//--------------------------------------------------------------------+
// Device Descriptors
//--------------------------------------------------------------------+
tusb_desc_device_t const desc_device =
{
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

    .iManufacturer      = STRID_MANUFACTURER,
    .iProduct           = STRID_PRODUCT,
    .iSerialNumber      = STRID_SERIAL,

    .bNumConfigurations = 0x01
};

// Invoked when received GET DEVICE DESCRIPTOR
// Application return pointer to descriptor
uint8_t const * tud_descriptor_device_cb(void)
{
  return (uint8_t const *) &desc_device;
}

//--------------------------------------------------------------------+
// HID Report Descriptor
//--------------------------------------------------------------------+

uint8_t const desc_hid_report[] =
{
  TUD_HID_REPORT_DESC_GENERIC_INOUT(CFG_TUD_HID_BUFSIZE)
};

// Invoked when received GET HID REPORT DESCRIPTOR
// Application return pointer to descriptor
// Descriptor contents must exist long enough for transfer to complete
uint8_t const * tud_hid_descriptor_report_cb(uint8_t itf)
{
  (void) itf;
  return desc_hid_report;
}


//--------------------------------------------------------------------+
// Configuration Descriptor
//--------------------------------------------------------------------+

#define CONFIG_TOTAL_LEN  (TUD_CONFIG_DESC_LEN + TUD_MSC_DESC_LEN + TUD_HID_INOUT_DESC_LEN + CFG_TUD_VENDOR*TUD_VENDOR_DESC_LEN)

#define EPNUM_MSC_OUT     0x01
#define EPNUM_MSC_IN      0x81

#define EPNUM_HID_OUT     0x02
#define EPNUM_HID_IN      0x82

#define EPNUM_VENDOR_OUT  0x03
#define EPNUM_VENDOR_IN   0x83

uint8_t const desc_configuration[] =
{
  // Config number, interface count, string index, total length, attribute, power in mA
  TUD_CONFIG_DESCRIPTOR(1, ITF_NUM_TOTAL, 0, CONFIG_TOTAL_LEN, TUSB_DESC_CONFIG_ATT_REMOTE_WAKEUP, 100),

  // Interface number, string index, EP Out & EP In address, EP size
  TUD_MSC_DESCRIPTOR(ITF_NUM_MSC, STRID_MSC, EPNUM_MSC_OUT, EPNUM_MSC_IN, TUD_OPT_HIGH_SPEED ? 512 : 64),

  // Interface number, string index, protocol, report descriptor len, EP In & Out address, size & polling interval
  TUD_HID_INOUT_DESCRIPTOR(ITF_NUM_HID, STRID_HID, HID_ITF_PROTOCOL_NONE, sizeof(desc_hid_report), EPNUM_HID_OUT, EPNUM_HID_IN, CFG_TUD_HID_BUFSIZE, 10),

#if CFG_TUD_VENDOR
  // Interface number, string index, EP Out & IN address, EP size
  TUD_VENDOR_DESCRIPTOR(ITF_NUM_VENDOR, STRID_VENDOR, EPNUM_VENDOR_OUT, EPNUM_VENDOR_IN, 64)
#endif

};


// Invoked when received GET CONFIGURATION DESCRIPTOR
// Application return pointer to descriptor
// Descriptor contents must exist long enough for transfer to complete
uint8_t const * tud_descriptor_configuration_cb(uint8_t index)
{
  (void) index; // for multiple configurations

  // TODO when device is highspeed, host is fullspeed.
  return desc_configuration;
}

//--------------------------------------------------------------------+
// String Descriptors
//--------------------------------------------------------------------+

// Serial is 64-bit DeviceID -> 16 chars len
static char desc_str_serial[1+16] = { 0 };

// array of pointer to string descriptors
char const* string_desc_arr [] =
{
  (const char[]) { 0x09, 0x04 }, // 0: is supported language is English (0x0409)
  USB_MANUFACTURER,              // 1: Manufacturer
  USB_PRODUCT,                   // 2: Product
  desc_str_serial,               // 3: Serials, use default MAC address
  "UF2",                         // 4: MSC Interface
  "HF2 HID",
  "HF2 WebUSB"
};

static uint16_t _desc_str[32+1];

// Invoked when received GET STRING DESCRIPTOR request
// Application return pointer to descriptor, whose contents must exist long enough for transfer to complete
uint16_t const* tud_descriptor_string_cb(uint8_t index, uint16_t langid)
{
  (void) langid;

  uint8_t chr_count;

  switch (index)
  {
    case STRID_LANGID:
      memcpy(&_desc_str[1], string_desc_arr[0], 2);
      chr_count = 1;
    break;

    // TODO light alternation such as +1 to prevent conflict with application
    case STRID_SERIAL:
    {
      uint8_t serial_id[16] TU_ATTR_ALIGNED(4);
      uint8_t serial_len;

      serial_len = board_usb_get_serial(serial_id);
      chr_count = 2*serial_len;

      for ( uint8_t i = 0; i < serial_len; i++ )
      {
        for ( uint8_t j = 0; j < 2; j++ )
        {
          const char nibble_to_hex[16] = {'0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F'};

          uint8_t nibble = (serial_id[i] >> (j * 4)) & 0xf;
          _desc_str[1 + i * 2 + (1 - j)] = nibble_to_hex[nibble]; // UTF-16-LE
        }
      }
    }
    break;

    default:
    {
      // Convert ASCII string into UTF-16
      if ( !(index < sizeof(string_desc_arr)/sizeof(string_desc_arr[0])) ) return NULL;

      const char* str = string_desc_arr[index];

      // Cap at max char
      chr_count = strlen(str);
      if ( chr_count > 31 ) chr_count = 31;

      for(uint8_t i=0; i<chr_count; i++)
      {
        _desc_str[1+i] = str[i];
      }
    }
    break;
  }

  // first byte is length (including header), second byte is string type
  _desc_str[0] = (TUSB_DESC_STRING << 8 ) | (2*chr_count + 2);

  return _desc_str;
}
