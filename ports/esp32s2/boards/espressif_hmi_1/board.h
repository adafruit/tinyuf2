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

#ifndef ESPRESSIF_HMI_1_H_
#define ESPRESSIF_HMI_1_H_

//--------------------------------------------------------------------+
// Button
//--------------------------------------------------------------------+

// Enter UF2 mode if GPIO is pressed while 2nd stage bootloader indicator
// is on e.g RGB = Purple. If it is GPIO0, user should not hold this while
// reset since that will instead run the 1st stage ROM bootloader
#define PIN_BUTTON_UF2        0

// GPIO that implement 1-bit memory with RC components which hold the
// pin value long enough for double reset detection.
// #define PIN_DOUBLE_RESET_RC   16

//--------------------------------------------------------------------+
// LED
//--------------------------------------------------------------------+

// GPIO connected to Neopixel data
#define NEOPIXEL_PIN          21

// Brightness percentage from 1 to 255
#define NEOPIXEL_BRIGHTNESS   0x30

// Number of neopixels
#define NEOPIXEL_NUMBER       1

//Peripheral power is enabled through I2C connected TCA9554
#define I2C_MASTER_SCL_IO           39
#define I2C_MASTER_SDA_IO           40
#define I2C_MASTER_NUM              0
#define I2C_MASTER_FREQ_HZ          400000
#define I2C_MASTER_TX_BUF_DISABLE   0
#define I2C_MASTER_RX_BUF_DISABLE   0
#define I2C_MASTER_TIMEOUT_MS       1000
#define I2C_WAIT                    40      //Timing (in microseconds) for I2C

#define TCA9554_ADDR                    0x20
#define TCA9554_INPUT_PORT_REG          0x00
#define TCA9554_OUTPUT_PORT_REG         0x01
#define TCA9554_POLARITY_INVERSION_REG  0x02
#define TCA9554_CONFIGURATION_REG       0x03
#define TCA9554_DEFAULT_CONFIG          0b10100000            
#define TCA9554_DEFAULT_VALUE           0b11100000             //Enable peripheral power and ws2812 data in
#define TCA9554_PERI_POWER_ON_VALUE     0b11100000             //Enable peripheral power and ws2812 data in
#define TCA9554_PERI_POWER_OFF_VALUE    0b11110000             //Disable Peripheral power

//--------------------------------------------------------------------+
// USB UF2
//--------------------------------------------------------------------+

#define USB_VID           0x303A
#define USB_PID           0x7000
#define USB_MANUFACTURER  "Espressif"
#define USB_PRODUCT       "HMI 1"

#define UF2_PRODUCT_NAME  USB_MANUFACTURER " " USB_PRODUCT
#define UF2_BOARD_ID      "ESP32S2-HMI-v1.1"
#define UF2_VOLUME_LABEL  "ESPHMI1BOOT"
#define UF2_INDEX_URL     "https://docs.espressif.com/projects/esp-idf/en/latest/esp32s2/hw-reference/esp32s2/user-guide-esp32-s2-kaluga-1-kit.html"


#endif
