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
#include "nvs.h"
#include "nvs_flash.h"
#include "bootloader_init.h"
#include "bootloader_utility.h"
#include "bootloader_common.h"

#include "esp32s2/rom/gpio.h"
#include "soc/cpu.h"
#include "hal/gpio_ll.h"

// Specific board header specified with -DBOARD=
#include "board.h"


// Initial delay in milliseconds to detect user interaction to enter UF2.
#define UF2_DETECTION_DELAY_MS       500

uint8_t const RGB_DOUBLE_TAP[] = { 0x80, 0x00, 0xff }; // Purple
uint8_t const RGB_OFF[]        = { 0x00, 0x00, 0x00 };

//--------------------------------------------------------------------+
//
//--------------------------------------------------------------------+
static const char *TAG = "boot";

static int select_partition_number(bootloader_state_t *bs);
static int selected_boot_partition(const bootloader_state_t *bs);

static void board_led_on(void);
static void board_led_off(void);

//--------------------------------------------------------------------+
// Get UF2 boot flag and clear it if set
//--------------------------------------------------------------------+

bool getBootIntoUF2Flag() {
  nvs_handle_t m_nvsHandle = 0;
//   int32_t flag = 0;

  ESP_GOTO_ON_ERROR(nvs_flash_init(), err, TAG, "initializing NVS failed");
  ESP_GOTO_ON_ERROR(nvs_open("storage", NVS_READWRITE, &m_nvsHandle), err, TAG, "opening storage file failed");
  ESP_GOTO_ON_ERROR(nvs_get_i32(m_nvsHandle, "uf2flag", &flag), err, TAG, "getting uf2flag failed");

  if (value == 1) {
    //reset flag and return
    value = 0
    ESP_GOTO_ON_ERROR(nvs_set_i32(m_nvsHandle, "uf2flag", flag), err, TAG, "resetting uf2flag failed");
    ESP_GOTO_ON_ERROR(nvs_commit(m_nvsHandle), err, TAG, "commiting file failed");
    return true;
  }

  return false;

  err:
    return false;
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

    RESET_REASON reset_reason = bootloader_common_get_reset_reason(0);
    if (reset_reason != DEEPSLEEP_RESET) {
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

        // UF2: check if Application want to load uf2 "bootloader" with uf2 boot flag.
        if ( boot_index != FACTORY_INDEX )
        {
          if ( reset_reason == RTC_SW_SYS_RESET )
          {
            if ( getBootIntoUF2Flag() ) {
              ESP_LOGI(TAG, "Detect application request to enter UF2 bootloader");
              boot_index = FACTORY_INDEX;
            }
          }
        }

        // UF2: check if GPIO0 is pressed and/or 1-bit RC on specific GPIO detect double reset
        // during this time. If yes then to load uf2 "bootloader".
        if ( boot_index != FACTORY_INDEX )
        {
          board_led_on();

#ifdef PIN_DOUBLE_RESET_RC
          // Double reset detect if board implements 1-bit memory with RC components
          PIN_INPUT_ENABLE(GPIO_PIN_MUX_REG[PIN_DOUBLE_RESET_RC]);
          if ( GPIO_INPUT_GET(PIN_DOUBLE_RESET_RC) == 1 )
          {
            ESP_LOGI(TAG, "Detect double reset using RC on GPIO %d to enter UF2 bootloader", PIN_DOUBLE_RESET_RC);
            boot_index = FACTORY_INDEX;
          }
          else
          {
            GPIO_OUTPUT_SET(PIN_DOUBLE_RESET_RC, 1);
          }
#endif

          if ( boot_index != FACTORY_INDEX )
          {
            gpio_pad_select_gpio(PIN_BUTTON_UF2);
            if (GPIO_PIN_MUX_REG[PIN_BUTTON_UF2]) {
              PIN_INPUT_ENABLE(GPIO_PIN_MUX_REG[PIN_BUTTON_UF2]);
            }
            gpio_pad_pullup(PIN_BUTTON_UF2);

            uint32_t tm_start = esp_log_early_timestamp();
            while (UF2_DETECTION_DELAY_MS > (esp_log_early_timestamp() - tm_start) )
            {
              if ( GPIO_INPUT_GET(PIN_BUTTON_UF2) == 0 )
              {
                ESP_LOGI(TAG, "Detect GPIO %d active to enter UF2 bootloader", PIN_BUTTON_UF2);

                // Simply return factory index without erasing any other partition
                boot_index = FACTORY_INDEX;
                break;
              }
            }
          }

#if PIN_DOUBLE_RESET_RC
          GPIO_OUTPUT_SET(PIN_DOUBLE_RESET_RC, 0);
#endif

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

//--------------------------------------------------------------------+
// Board LED Indicator
//--------------------------------------------------------------------+

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

#ifdef NEOPIXEL_PIN

static inline uint8_t color_brightness(uint8_t color, uint8_t brightness)
{
  return (uint8_t) ((color*brightness) >> 8);
}

static void board_neopixel_set(uint32_t num_pin, uint8_t const rgb[])
{
  // WS2812B should be
  uint32_t const time0  = ns2cycle(400);
  uint32_t const time1  = ns2cycle(800);
  uint32_t const period = ns2cycle(1250);

  uint8_t pixels[3*NEOPIXEL_NUMBER];
  for(uint32_t i=0; i<NEOPIXEL_NUMBER; i++)
  {
    // Note: WS2812 color order is GRB
    pixels[3*i  ] = color_brightness(rgb[1], NEOPIXEL_BRIGHTNESS);
    pixels[3*i+1] = color_brightness(rgb[0], NEOPIXEL_BRIGHTNESS);
    pixels[3*i+2] = color_brightness(rgb[2], NEOPIXEL_BRIGHTNESS);
  }

  uint32_t cyc = 0;
  for(uint16_t n=0; n<sizeof(pixels); n++) {
    uint8_t const pix = pixels[n];

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
#endif

#ifdef DOTSTAR_PIN_DATA
//Bit bang out 8 bits
static void SPI_write(int32_t pin_data,uint32_t pin_sck,uint8_t c)
{
  uint8_t i;
  for (i=0; i<8 ;i++)
  {
    if (!(c&0x80)) {
      gpio_ll_set_level(&GPIO, pin_data, 0);
    }
    else {
      gpio_ll_set_level(&GPIO, pin_data, 1);
    }
    delay_cycle( ns2cycle(200000) ) ;
    gpio_ll_set_level(&GPIO, pin_sck, 1);
    c<<=1;
    delay_cycle( ns2cycle(200000) ) ;
    gpio_ll_set_level(&GPIO, pin_sck, 0);
    delay_cycle( ns2cycle(200000) );
  }
}

static void board_dotstar_set(uint32_t pin_data, uint32_t pin_sck, uint8_t const rgb[])
{
  // convert from 0-255 (8 bit) to 0-31 (5 bit)
  uint8_t const ds_brightness = (DOTSTAR_BRIGHTNESS * 32) / 256;

  // Start frame
  SPI_write(pin_data, pin_sck, 0x00);
  SPI_write(pin_data, pin_sck, 0x00);
  SPI_write(pin_data, pin_sck, 0x00);
  SPI_write(pin_data, pin_sck, 0x00);

  for(uint32_t i=0; i<DOTSTAR_NUMBER; i++)
  {
    SPI_write(pin_data, pin_sck, 0xE0 | ds_brightness);

    // DotStar APA102 color order is BGR
    SPI_write(pin_data, pin_sck, rgb[2]);
    SPI_write(pin_data, pin_sck, rgb[1]);
    SPI_write(pin_data, pin_sck, rgb[0]);
  }

  // End frame
  for(uint32_t i=0; i < (DOTSTAR_NUMBER+15)/16; i++)
  {
    SPI_write(pin_data, pin_sck, 0xff);
  }
}
#endif

static void board_led_on(void)
{
#ifdef NEOPIXEL_PIN

  #ifdef NEOPIXEL_POWER_PIN
  gpio_pad_select_gpio(NEOPIXEL_POWER_PIN);
  gpio_ll_input_disable(&GPIO, NEOPIXEL_POWER_PIN);
  gpio_ll_output_enable(&GPIO, NEOPIXEL_POWER_PIN);
  gpio_ll_set_level(&GPIO, NEOPIXEL_POWER_PIN, NEOPIXEL_POWER_STATE);
  #endif

  gpio_pad_select_gpio(NEOPIXEL_PIN);
  gpio_ll_input_disable(&GPIO, NEOPIXEL_PIN);
  gpio_ll_output_enable(&GPIO, NEOPIXEL_PIN);
  gpio_ll_set_level(&GPIO, NEOPIXEL_PIN, 0);
#endif

#ifdef DOTSTAR_PIN_DATA
  gpio_pad_select_gpio(DOTSTAR_PIN_DATA);
  gpio_ll_input_disable(&GPIO, DOTSTAR_PIN_DATA);
  gpio_ll_output_enable(&GPIO, DOTSTAR_PIN_DATA);
  gpio_ll_set_level(&GPIO, DOTSTAR_PIN_DATA, 0);

  gpio_pad_select_gpio(DOTSTAR_PIN_SCK);
  gpio_ll_input_disable(&GPIO, DOTSTAR_PIN_SCK);
  gpio_ll_output_enable(&GPIO, DOTSTAR_PIN_SCK);
  gpio_ll_set_level(&GPIO, DOTSTAR_PIN_SCK, 0);

  #ifdef DOTSTAR_PIN_PWR
  gpio_pad_select_gpio(DOTSTAR_PIN_PWR);
  gpio_ll_input_disable(&GPIO, DOTSTAR_PIN_PWR);
  gpio_ll_output_enable(&GPIO, DOTSTAR_PIN_PWR);
  gpio_ll_set_level(&GPIO, DOTSTAR_PIN_PWR, DOTSTAR_POWER_STATE);
  #endif
#endif

#ifdef LED_PIN
  gpio_pad_select_gpio(LED_PIN);
  gpio_ll_input_disable(&GPIO, LED_PIN);
  gpio_ll_output_enable(&GPIO, LED_PIN);
  gpio_ll_set_level(&GPIO, LED_PIN, LED_STATE_ON);
#endif

  // Need at least 200 us for initial delay although Neopixel reset time is only 50 us
  delay_cycle( ns2cycle(200000) ) ;

#ifdef NEOPIXEL_PIN
  board_neopixel_set(NEOPIXEL_PIN, RGB_DOUBLE_TAP);
#endif

#ifdef LED_PIN
  gpio_ll_set_level(&GPIO, LED_PIN, 1);
#endif

#ifdef DOTSTAR_PIN_DATA
  board_dotstar_set(DOTSTAR_PIN_DATA, DOTSTAR_PIN_SCK, RGB_DOUBLE_TAP);
#endif
}

static void board_led_off(void)
{
#ifdef NEOPIXEL_PIN
  board_neopixel_set(NEOPIXEL_PIN, RGB_OFF);

  // Neopixel reset time
  delay_cycle( ns2cycle(200000) ) ;

  // TODO how to de-select GPIO pad to set it back to default state !?
  gpio_ll_output_disable(&GPIO, NEOPIXEL_PIN);

  #ifdef NEOPIXEL_POWER_PIN
  gpio_ll_set_level(&GPIO, NEOPIXEL_POWER_PIN, 1-NEOPIXEL_POWER_STATE);
  gpio_ll_output_disable(&GPIO, NEOPIXEL_POWER_PIN);
  #endif
#endif

#ifdef DOTSTAR_PIN_DATA
  board_dotstar_set(DOTSTAR_PIN_DATA, DOTSTAR_PIN_SCK, RGB_OFF);

  gpio_ll_output_disable(&GPIO, DOTSTAR_PIN_DATA);
  gpio_ll_output_disable(&GPIO, DOTSTAR_PIN_SCK);

  #ifdef DOTSTAR_PIN_PWR
  gpio_ll_set_level(&GPIO, DOTSTAR_PIN_PWR, 1-DOTSTAR_POWER_STATE);
  gpio_ll_output_disable(&GPIO, DOTSTAR_PIN_PWR);
  #endif
#endif

#ifdef LED_PIN
  gpio_ll_set_level(&GPIO, LED_PIN, 1-LED_STATE_ON);
  gpio_ll_output_disable(&GPIO, LED_PIN);
#endif
}
