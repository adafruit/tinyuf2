// Copyright 2015-2019 Espressif Systems (Shanghai) PTE LTD
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
#include <stdbool.h>
#include "esp_log.h"
#include "bootloader_init.h"
#include "bootloader_utility.h"
#include "bootloader_common.h"

static const char *TAG = "boot";

static int select_partition_number(bootloader_state_t *bs);
static int selected_boot_partition(const bootloader_state_t *bs);

#include "esp32s2/rom/gpio.h"
#include "soc/cpu.h"
#include "hal/gpio_ll.h"

//#define LED_PIN               18 // v1.2 and later
#define LED_PIN               17 // v1.1

// min 0, max 255
#define LED_BRIGHTNESS    0x20

static inline uint32_t ns2cycle(uint32_t ns)
{
  extern uint32_t g_ticks_per_us_pro; // e.g 80 for 80 Mhz
  return (g_ticks_per_us_pro*ns) / 1000;
}

static inline uint32_t delay_cycle(uint32_t cycle)
{
  uint32_t ccount;
  uint32_t start = esp_cpu_get_ccount();
  while( (ccount = esp_cpu_get_ccount()) - start < cycle ) {}
  return ccount;
}

void board_neopixel_set(uint32_t num_pin, uint8_t pixels[], uint32_t numBytes)
{
  // WS2812B should be
   uint32_t const time0 = ns2cycle(400);
   uint32_t const time1  = ns2cycle(800);
   uint32_t const period = ns2cycle(1250);

  uint32_t cyc = 0;
  for(uint16_t n=0; n<numBytes; n++) {
    uint8_t pix = ((*pixels++) * LED_BRIGHTNESS) >> 8;

    for(uint8_t mask = 0x80; mask > 0; mask >>= 1) {
      uint32_t ccount;
      while( (ccount = esp_cpu_get_ccount()) - cyc < period ) {}

      // gpio_ll_set_level() only take 6 cycles, while GPIO_OUTPUT_SET() take 40 cycles to set/clear
      gpio_ll_set_level(&GPIO, num_pin, 1);

      cyc = ccount;
      uint32_t const t_hi = (pix & mask) ? time1 : time0;
      while( (ccount = esp_cpu_get_ccount()) - cyc < t_hi ) {}

      gpio_ll_set_level(&GPIO, num_pin, 0);
    }
  }

  while(esp_cpu_get_ccount() - cyc < period) {}
}

void board_led_on(void)
{
  gpio_pad_select_gpio(LED_PIN);
  gpio_ll_input_disable(&GPIO, LED_PIN);
  gpio_ll_output_enable(&GPIO, LED_PIN);
  gpio_ll_set_level(&GPIO, LED_PIN, 0);

  // Need at least 200 us for initial delay although Neopixel reset time is only 50 us
  delay_cycle( ns2cycle(200000) ) ;

  // Note: WS2812 color order is GRB
  uint8_t pixels[3] = { 0x00, 0x86, 0xb3 };
  board_neopixel_set(LED_PIN, pixels, sizeof(pixels));
}

void board_led_off(void)
{
  uint8_t pixels[3] = { 0x00, 0x00, 0x00 };
  board_neopixel_set(LED_PIN, pixels, sizeof(pixels));

  // Neopixel 50us reset time
  delay_cycle( ns2cycle(50000) ) ;

  // TODO how to de-select GPIO pad to set it back to default state !?
  gpio_ll_output_disable(&GPIO, LED_PIN);
}

/*
 * We arrive here after the ROM bootloader finished loading this second stage bootloader from flash.
 * The hardware is mostly uninitialized, flash cache is down and the app CPU is in reset.
 * We do have a stack, so we can do the initialization in C.
 */
void __attribute__((noreturn)) call_start_cpu0(void)
{
    // 1. Hardware initialization
    if (bootloader_init() != ESP_OK) {
        bootloader_reset();
    }

#ifdef CONFIG_BOOTLOADER_SKIP_VALIDATE_IN_DEEP_SLEEP
    // If this boot is a wake up from the deep sleep then go to the short way,
    // try to load the application which worked before deep sleep.
    // It skips a lot of checks due to it was done before (while first boot).
    bootloader_utility_load_boot_image_from_deep_sleep();
    // If it is not successful try to load an application as usual.
#endif

    // 2. Select the number of boot partition
    bootloader_state_t bs = {0};
    int boot_index = select_partition_number(&bs);
    if (boot_index == INVALID_INDEX) {
        bootloader_reset();
    }

    // 3. Load the app image for booting
    bootloader_utility_load_boot_image(&bs, boot_index);
}

// Select the number of boot partition
static int select_partition_number(bootloader_state_t *bs)
{
    // 1. Load partition table
    if (!bootloader_utility_load_partition_table(bs)) {
        ESP_LOGE(TAG, "load partition table error!");
        return INVALID_INDEX;
    }

    // 2. Select the number of boot partition
    return selected_boot_partition(bs);
}

/*
 * Selects a boot partition.
 * The conditions for switching to another firmware are checked.
 */
static int selected_boot_partition(const bootloader_state_t *bs)
{
    int boot_index = bootloader_utility_get_selected_boot_partition(bs);
    if (boot_index == INVALID_INDEX) {
        return boot_index; // Unrecoverable failure (not due to corrupt ota data or bad partition contents)
    }
    if (bootloader_common_get_reset_reason(0) != DEEPSLEEP_RESET) {
        // Factory firmware.
#ifdef CONFIG_BOOTLOADER_FACTORY_RESET
        if (bootloader_common_check_long_hold_gpio(CONFIG_BOOTLOADER_NUM_PIN_FACTORY_RESET, CONFIG_BOOTLOADER_HOLD_TIME_GPIO) == 1) {
            ESP_LOGI(TAG, "Detect a condition of the factory reset");
            bool ota_data_erase = false;
#ifdef CONFIG_BOOTLOADER_OTA_DATA_ERASE
            ota_data_erase = true;
#endif
            const char *list_erase = CONFIG_BOOTLOADER_DATA_FACTORY_RESET;
            ESP_LOGI(TAG, "Data partitions to erase: %s", list_erase);
            if (bootloader_common_erase_part_type_data(list_erase, ota_data_erase) == false) {
                ESP_LOGE(TAG, "Not all partitions were erased");
            }
            return bootloader_utility_get_selected_boot_partition(bs);
        }
#endif
        // TEST firmware.
#ifdef CONFIG_BOOTLOADER_APP_TEST
        if (bootloader_common_check_long_hold_gpio(CONFIG_BOOTLOADER_NUM_PIN_APP_TEST, CONFIG_BOOTLOADER_HOLD_TIME_GPIO) == 1) {
            ESP_LOGI(TAG, "Detect a boot condition of the test firmware");
            if (bs->test.offset != 0) {
                boot_index = TEST_APP_INDEX;
                return boot_index;
            } else {
                ESP_LOGE(TAG, "Test firmware is not found in partition table");
                return INVALID_INDEX;
            }
        }
#endif
        // UF2 modification to detect if GPIO0 is pressed during this time to load uf2 "bootloader" app
        if ( boot_index != FACTORY_INDEX )
        {
          board_led_on();

          uint32_t num_pin = 0;
          gpio_pad_select_gpio(num_pin);
          if (GPIO_PIN_MUX_REG[num_pin]) {
            PIN_INPUT_ENABLE(GPIO_PIN_MUX_REG[num_pin]);
          }
          gpio_pad_pullup(num_pin);

          uint32_t tm_start = esp_log_early_timestamp();
          while (500 > (esp_log_early_timestamp() - tm_start) )
          {
            if ( GPIO_INPUT_GET(num_pin) == 0 )
            {
              ESP_LOGI(TAG, "Detect a condition of the UF2 Bootloader");

              // Simply return factory index without erasing any other partition
              boot_index = FACTORY_INDEX;
              break;
            }
          }

          board_led_off();
        }

        // Customer implementation.
        // if (gpio_pin_1 == true && ...){
        //     boot_index = required_boot_partition;
        // } ...
    }
    return boot_index;
}

// Return global reent struct if any newlib functions are linked to bootloader
struct _reent *__getreent(void)
{
    return _GLOBAL_REENT;
}
