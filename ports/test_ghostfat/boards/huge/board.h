/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2018 Ha Thach for Adafruit Industries
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

// NOTE: This is a HUGE test image ... 1.5GiB if dumped fully
//       FAT16 still works, using 64KiB clusters
//       The flash size is set to 256MiB (0x1000_0000 == 268435456 == 256 * 1024 * 1024 bytes)
//       The UF2 file thus should take 0x10_0000 512-byte sectors, and be 512MiB in size.
//
//       Ghostfat appears to have a bug in the generated .UF2 file.
//       TODO: determine why the .UF2 file is generated with a size of 0x80_0000 bytes.
//

#ifndef BOARD_H_
#define BOARD_H_

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID           0x0000
#define USB_PID           0x0000
#define USB_MANUFACTURER  "Adafruit"
#define USB_PRODUCT       "SELFTEST"

#define UF2_PRODUCT_NAME  USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID      "Test_Huge"
#define UF2_VOLUME_LABEL  "Test_Huge"
#define UF2_INDEX_URL     "https://www.adafruit.com"

#endif
