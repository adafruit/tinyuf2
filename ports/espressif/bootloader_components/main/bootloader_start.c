/*
 * SPDX-FileCopyrightText: 2015-2022 Espressif Systems (Shanghai) CO LTD
 *
 * SPDX-License-Identifier: Apache-2.0
 */
#include <stdbool.h>
#include "esp_log.h"
#include "esp_rom_sys.h"
#include "bootloader_init.h"
#include "bootloader_utility.h"
#include "bootloader_common.h"
#include "bootloader_hooks.h"

#include "rom/ets_sys.h"
#include "rom/rtc.h"
#include "esp_rom_gpio.h"
#include "esp_cpu.h"
#include "hal/gpio_hal.h"

// Specific board header specified with -DBOARD=
#include "board.h"

#ifdef TCA9554_ADDR
  #include "hal/i2c_types.h"
  // Using GPIO expander requires long reset delay (somehow)
  #define NEOPIXEL_RESET_DELAY      ns2cycle(1000*1000)
#endif

#ifndef NEOPIXEL_RESET_DELAY
  // Need at least 200 us for initial delay although Neopixel reset time is only 50 us
  #define NEOPIXEL_RESET_DELAY      ns2cycle(200*1000)
#endif

// Reset Reason Hint to enter UF2. Check out esp_reset_reason_t for other Espressif pre-defined values
#define APP_REQUEST_UF2_RESET_HINT   0x11F2

#ifndef UF2_DETECTION_DELAY_MS
  // Initial delay in milliseconds to detect user interaction to enter UF2.
  #define UF2_DETECTION_DELAY_MS     500
#endif

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
// Get Reset Reason Hint requested by Application to enter UF2
//--------------------------------------------------------------------+

// copied from components/esp_system/port/soc/esp32sx/reset_reason.c
// since esp_system is not included with bootloader build
#define RST_REASON_BIT  0x80000000
#define RST_REASON_MASK 0x7FFF
#define RST_REASON_SHIFT 16

uint32_t esp_reset_reason_get_hint(void) {
    uint32_t reset_reason_hint = REG_READ(RTC_RESET_CAUSE_REG);
    uint32_t high = (reset_reason_hint >> RST_REASON_SHIFT) & RST_REASON_MASK;
    uint32_t low = reset_reason_hint & RST_REASON_MASK;
    if ((reset_reason_hint & RST_REASON_BIT) == 0 || high != low) {
        return 0;
    }
    return low;
}

static void esp_reset_reason_clear_hint(void) {
    REG_WRITE(RTC_RESET_CAUSE_REG, 0);
}

/*
 * We arrive here after the ROM bootloader finished loading this second stage bootloader from flash.
 * The hardware is mostly uninitialized, flash cache is down and the app CPU is in reset.
 * We do have a stack, so we can do the initialization in C.
 */
void __attribute__((noreturn)) call_start_cpu0(void)
{
    // (0. Call the before-init hook, if available)
    if (bootloader_before_init) {
        bootloader_before_init();
    }

    // 1. Hardware initialization
    if (bootloader_init() != ESP_OK) {
        bootloader_reset();
    }

    // (1.1 Call the after-init hook, if available)
    if (bootloader_after_init) {
        bootloader_after_init();
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
static int selected_boot_partition(const bootloader_state_t *bs) {
    int boot_index = bootloader_utility_get_selected_boot_partition(bs);
    if (boot_index == INVALID_INDEX) {
        return boot_index; // Unrecoverable failure (not due to corrupt ota data or bad partition contents)
    }

    soc_reset_reason_t reset_reason = esp_rom_get_reset_reason(0);
    ESP_LOGI(TAG, "Reset Reason = %d", reset_reason);
    if (reset_reason != RESET_REASON_CORE_DEEP_SLEEP) {
        // Factory firmware.
#ifdef CONFIG_BOOTLOADER_FACTORY_RESET
        bool reset_level = false;
#if CONFIG_BOOTLOADER_FACTORY_RESET_PIN_HIGH
        reset_level = true;
#endif
        if (bootloader_common_check_long_hold_gpio_level(CONFIG_BOOTLOADER_NUM_PIN_FACTORY_RESET, CONFIG_BOOTLOADER_HOLD_TIME_GPIO, reset_level) == GPIO_LONG_HOLD) {
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
#ifdef CONFIG_BOOTLOADER_RESERVE_RTC_MEM
            bootloader_common_set_rtc_retain_mem_factory_reset_state();
#endif
            return bootloader_utility_get_selected_boot_partition(bs);
        }
#endif // CONFIG_BOOTLOADER_FACTORY_RESET
        // TEST firmware.
#ifdef CONFIG_BOOTLOADER_APP_TEST
        bool app_test_level = false;
#if CONFIG_BOOTLOADER_APP_TEST_PIN_HIGH
        app_test_level = true;
#endif
        if (bootloader_common_check_long_hold_gpio_level(CONFIG_BOOTLOADER_NUM_PIN_APP_TEST, CONFIG_BOOTLOADER_HOLD_TIME_GPIO, app_test_level) == GPIO_LONG_HOLD) {
            ESP_LOGI(TAG, "Detect a boot condition of the test firmware");
            if (bs->test.offset != 0) {
                boot_index = TEST_APP_INDEX;
                return boot_index;
            } else {
                ESP_LOGE(TAG, "Test firmware is not found in partition table");
                return INVALID_INDEX;
            }
        }
#endif // CONFIG_BOOTLOADER_APP_TEST

        // TinyUF2: check if Application want to load uf2 "bootloader" with reset reason hint.
        if ( boot_index != FACTORY_INDEX ) {
          // Application request to enter UF2 with Software Reset with reason hint
          if ( reset_reason == RESET_REASON_CORE_SW ||  reset_reason == RESET_REASON_CPU0_SW ) {
            uint32_t const reset_hint = (uint32_t) esp_reset_reason_get_hint();
            ESP_LOGI(TAG, "Reset hint = %d", reset_hint);
            if ( APP_REQUEST_UF2_RESET_HINT == reset_hint ) {
              esp_reset_reason_clear_hint(); // clear the hint
              ESP_LOGI(TAG, "Detect application request to enter UF2 bootloader");
              boot_index = FACTORY_INDEX;
            }
          }
        }

        // TinyUF2: when reset by EN/nRST pin: check if GPIO0 is pressed and/or 1-bit RC on specific GPIO detect double reset
        // during this time. If yes then to load uf2 "bootloader".
        if (boot_index != FACTORY_INDEX && reset_reason == RESET_REASON_CHIP_POWER_ON) {
          #ifdef PIN_DOUBLE_RESET_RC
          // Double reset detect if board implements 1-bit memory with RC components
          esp_rom_gpio_pad_select_gpio(PIN_DOUBLE_RESET_RC);
          PIN_INPUT_ENABLE(GPIO_PIN_MUX_REG[PIN_DOUBLE_RESET_RC]);
          if ( gpio_ll_get_level(&GPIO, PIN_DOUBLE_RESET_RC) == 1 ) {
            // RC pin is already high, double reset detected
            ESP_LOGI(TAG, "Detect double reset using RC on GPIO %d to enter UF2 bootloader", PIN_DOUBLE_RESET_RC);
            boot_index = FACTORY_INDEX;
          }
          else {
            // Set to high to charge the RC, indicating we are in reset
            gpio_ll_output_enable(&GPIO, PIN_DOUBLE_RESET_RC);
            gpio_ll_set_level(&GPIO, PIN_DOUBLE_RESET_RC, 1);
          }
          #endif

          if (boot_index != FACTORY_INDEX) {
            #if SOC_USB_SERIAL_JTAG_SUPPORTED
            // startup with USB JTAG, while delaying here, USB JTAG will be enumerated which can cause confusion when
            // switching to OTG in application. Switch to OTG PHY here to avoid this.
            uint32_t const rtc_cntl_usb_conf = READ_PERI_REG(RTC_CNTL_USB_CONF_REG);
            SET_PERI_REG_MASK(RTC_CNTL_USB_CONF_REG,
                              RTC_CNTL_SW_HW_USB_PHY_SEL | RTC_CNTL_SW_USB_PHY_SEL | RTC_CNTL_USB_PAD_ENABLE);
            #endif

            if (UF2_DETECTION_DELAY_MS > 0){
              board_led_on();
            }

            esp_rom_gpio_pad_select_gpio(PIN_BUTTON_UF2);
            PIN_INPUT_ENABLE(GPIO_PIN_MUX_REG[PIN_BUTTON_UF2]);
            esp_rom_gpio_pad_pullup_only(PIN_BUTTON_UF2);

            // run the GPIO detection at least once even if UF2_DETECTION_DELAY_MS is set to zero
            uint32_t tm_start = esp_log_early_timestamp();
            do {
              if ( gpio_ll_get_level(&GPIO, PIN_BUTTON_UF2) == 0 ) {
                ESP_LOGI(TAG, "Detect GPIO %d active to enter UF2 bootloader", PIN_BUTTON_UF2);
                boot_index = FACTORY_INDEX;
                break;
              }
            } while (UF2_DETECTION_DELAY_MS > (esp_log_early_timestamp() - tm_start) );

            if (UF2_DETECTION_DELAY_MS > 0){
              board_led_off();
            }

            #if SOC_USB_SERIAL_JTAG_SUPPORTED
            WRITE_PERI_REG(RTC_CNTL_USB_CONF_REG, rtc_cntl_usb_conf);
            #endif
          }

#if PIN_DOUBLE_RESET_RC
          // Set to low to discharge the RC
          gpio_ll_output_enable(&GPIO, PIN_DOUBLE_RESET_RC);
          gpio_ll_set_level(&GPIO, PIN_DOUBLE_RESET_RC, 0);
          gpio_ll_output_disable(&GPIO, PIN_DOUBLE_RESET_RC);
#endif
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

static inline uint32_t ns2cycle(uint32_t ns) {
  uint32_t tick_per_us;

#if CONFIG_IDF_TARGET_ESP32S3
  tick_per_us = ets_get_cpu_frequency();
#else // ESP32S2
  extern uint32_t g_ticks_per_us_pro;
  tick_per_us = g_ticks_per_us_pro;
#endif

  return (tick_per_us*ns) / 1000;
}

static inline uint32_t delay_cycle(uint32_t cycle) {
  uint32_t ccount;
  uint32_t start = esp_cpu_get_cycle_count();
  while( (ccount = esp_cpu_get_cycle_count()) - start < cycle ) {}
  return ccount;
}

#ifdef TCA9554_ADDR

//  Derived from https://github.com/bitbank2/BitBang_I2C  Larry Bank
#define LOW   0x00
#define HIGH  0x01
#define ACK   0x00
#define NACK  0x01
#define CLOCK_STRETCH_TIMEOUT   1000

#endif

#ifdef NEOPIXEL_PIN

static inline uint8_t color_brightness(uint8_t color, uint8_t brightness) {
  return (uint8_t) ((color*brightness) >> 8);
}

static void board_neopixel_set(uint32_t num_pin, uint8_t const rgb[]) {
  // WS2812B should be
  uint32_t const time0  = ns2cycle(400);
  uint32_t const time1  = ns2cycle(800);
  uint32_t const period = ns2cycle(1250);

  uint8_t pixels[3*NEOPIXEL_NUMBER];
  for(uint32_t i=0; i<NEOPIXEL_NUMBER; i++) {
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
      while( (ccount = esp_cpu_get_cycle_count()) - cyc < period ) {}

      // gpio_ll_set_level() only take 6 cycles, while GPIO_OUTPUT_SET() take 40 cycles to set/clear
      gpio_ll_set_level(&GPIO, num_pin, 1);

      cyc = ccount;
      uint32_t const t_hi = (pix & mask) ? time1 : time0;
      while( (ccount = esp_cpu_get_cycle_count()) - cyc < t_hi ) {}

      gpio_ll_set_level(&GPIO, num_pin, 0);
    }
  }

  while(esp_cpu_get_cycle_count() - cyc < period) {}
}
#endif

#ifdef DOTSTAR_PIN_DATA
//Bit bang out 8 bits
static void SPI_write(int32_t pin_data,uint32_t pin_sck,uint8_t c) {
  uint8_t i;
  for (i=0; i<8 ;i++) {
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

static void board_dotstar_set(uint32_t pin_data, uint32_t pin_sck, uint8_t const rgb[]) {
  // convert from 0-255 (8 bit) to 0-31 (5 bit)
  uint8_t const ds_brightness = (DOTSTAR_BRIGHTNESS * 32) / 256;

  // Start frame
  SPI_write(pin_data, pin_sck, 0x00);
  SPI_write(pin_data, pin_sck, 0x00);
  SPI_write(pin_data, pin_sck, 0x00);
  SPI_write(pin_data, pin_sck, 0x00);

  for(uint32_t i=0; i<DOTSTAR_NUMBER; i++) {
    SPI_write(pin_data, pin_sck, 0xE0 | ds_brightness);

    // DotStar APA102 color order is BGR
    SPI_write(pin_data, pin_sck, rgb[2]);
    SPI_write(pin_data, pin_sck, rgb[1]);
    SPI_write(pin_data, pin_sck, rgb[0]);
  }

  // End frame
  for(uint32_t i=0; i < (DOTSTAR_NUMBER+15)/16; i++) {
    SPI_write(pin_data, pin_sck, 0xff);
  }
}
#endif

#ifdef TCA9554_ADDR
// Write one byte to I2C bus
uint8_t sw_i2c_write_byte(uint8_t b) {
  uint8_t ack;

  //Shift out 8 bits
  for (uint8_t mask=0x80; mask!=0; mask>>=1) {
    if (mask & b) {
      gpio_ll_set_level(&GPIO, I2C_MASTER_SDA_IO, HIGH);
    }
    else {
      gpio_ll_set_level(&GPIO, I2C_MASTER_SDA_IO, LOW);
    }
    delay_cycle( ns2cycle(I2C_WAIT/2*1000) ) ;
    gpio_ll_set_level(&GPIO, I2C_MASTER_SCL_IO, HIGH);
    delay_cycle( ns2cycle(I2C_WAIT/2*1000) ) ;
    gpio_ll_set_level(&GPIO, I2C_MASTER_SCL_IO, LOW);
  }

  // Wait for ACK/NACK
  delay_cycle( ns2cycle(I2C_WAIT/2*1000) ) ;
  gpio_ll_set_level(&GPIO, I2C_MASTER_SDA_IO, HIGH);
  gpio_ll_set_level(&GPIO, I2C_MASTER_SCL_IO, HIGH);
  esp_rom_delay_us(I2C_WAIT);
  ack = gpio_ll_get_level( &GPIO, I2C_MASTER_SDA_IO);
  gpio_ll_set_level( &GPIO, I2C_MASTER_SCL_IO, LOW);
  gpio_ll_set_level(&GPIO, I2C_MASTER_SDA_IO, LOW);
  return ack == 0;
}

// I2C Start and Address
void sw_i2c_begin(uint8_t address) {
  // Start signal
  gpio_ll_set_level(&GPIO, I2C_MASTER_SDA_IO, LOW);
  delay_cycle( ns2cycle(I2C_WAIT*1000) ) ;
  gpio_ll_set_level(&GPIO, I2C_MASTER_SCL_IO, LOW);

  // Address the device
  sw_i2c_write_byte(address);
}

void sw_i2c_end() {
  gpio_ll_set_level(&GPIO, I2C_MASTER_SDA_IO, LOW);
  delay_cycle( ns2cycle(I2C_WAIT*1000) ) ;
  gpio_ll_set_level(&GPIO, I2C_MASTER_SCL_IO, HIGH);
  delay_cycle( ns2cycle(I2C_WAIT*1000) ) ;
  gpio_ll_set_level(&GPIO, I2C_MASTER_SDA_IO, HIGH);
}

// Initialize I2C pins
void sw_i2c_init() {
  esp_rom_gpio_pad_select_gpio(I2C_MASTER_SDA_IO);
  gpio_ll_input_enable(&GPIO, I2C_MASTER_SDA_IO);
  gpio_ll_output_enable(&GPIO, I2C_MASTER_SDA_IO);
  gpio_ll_od_enable(&GPIO, I2C_MASTER_SDA_IO);
  gpio_ll_pullup_en(&GPIO, I2C_MASTER_SDA_IO);
  gpio_ll_pulldown_dis(&GPIO, I2C_MASTER_SDA_IO);
  gpio_ll_intr_disable(&GPIO, I2C_MASTER_SDA_IO);
  gpio_ll_set_level(&GPIO, I2C_MASTER_SDA_IO, HIGH);

  esp_rom_gpio_pad_select_gpio(I2C_MASTER_SCL_IO);
  gpio_ll_input_disable(&GPIO, I2C_MASTER_SCL_IO);
  gpio_ll_output_enable(&GPIO, I2C_MASTER_SCL_IO);
  gpio_ll_od_enable(&GPIO, I2C_MASTER_SCL_IO);
  gpio_ll_pullup_en(&GPIO, I2C_MASTER_SCL_IO);
  gpio_ll_pulldown_dis(&GPIO, I2C_MASTER_SCL_IO);
  gpio_ll_intr_disable(&GPIO, I2C_MASTER_SCL_IO);
  gpio_ll_set_level(&GPIO, I2C_MASTER_SCL_IO, HIGH);
}

//Turn on Peripheral power.
void init_tca9554() {
  sw_i2c_begin(TCA9554_ADDR << 1);
  sw_i2c_write_byte(TCA9554_CONFIGURATION_REG);
  sw_i2c_write_byte(TCA9554_DEFAULT_CONFIG);
  sw_i2c_end();

  delay_cycle( ns2cycle(30000*1000) ) ;

  sw_i2c_begin(TCA9554_ADDR << 1);
  sw_i2c_write_byte(TCA9554_OUTPUT_PORT_REG);
  sw_i2c_write_byte(TCA9554_PERI_POWER_ON_VALUE);
  sw_i2c_end();
}
#endif

static void board_led_on(void) {
#ifdef NEOPIXEL_PIN
  #ifdef TCA9554_ADDR
  sw_i2c_init();
  // For some reason this delay is required after the pins are initialized before being used.
  delay_cycle( ns2cycle(30000*1000) );
  init_tca9554();
  #endif

  #ifdef NEOPIXEL_POWER_PIN
  esp_rom_gpio_pad_select_gpio(NEOPIXEL_POWER_PIN);
  gpio_ll_input_disable(&GPIO, NEOPIXEL_POWER_PIN);
  gpio_ll_output_enable(&GPIO, NEOPIXEL_POWER_PIN);
  gpio_ll_set_level(&GPIO, NEOPIXEL_POWER_PIN, NEOPIXEL_POWER_STATE);
  #endif

  esp_rom_gpio_pad_select_gpio(NEOPIXEL_PIN);
  gpio_ll_input_disable(&GPIO, NEOPIXEL_PIN);
  gpio_ll_output_enable(&GPIO, NEOPIXEL_PIN);
  gpio_ll_set_level(&GPIO, NEOPIXEL_PIN, 0);

  // Need at least 200 us for initial delay although Neopixel reset time is only 50 us
  delay_cycle( NEOPIXEL_RESET_DELAY ) ;

  board_neopixel_set(NEOPIXEL_PIN, RGB_DOUBLE_TAP);
#endif

#ifdef DOTSTAR_PIN_DATA
  esp_rom_gpio_pad_select_gpio(DOTSTAR_PIN_DATA);
  gpio_ll_input_disable(&GPIO, DOTSTAR_PIN_DATA);
  gpio_ll_output_enable(&GPIO, DOTSTAR_PIN_DATA);
  gpio_ll_set_level(&GPIO, DOTSTAR_PIN_DATA, 0);

  esp_rom_gpio_pad_select_gpio(DOTSTAR_PIN_SCK);
  gpio_ll_input_disable(&GPIO, DOTSTAR_PIN_SCK);
  gpio_ll_output_enable(&GPIO, DOTSTAR_PIN_SCK);
  gpio_ll_set_level(&GPIO, DOTSTAR_PIN_SCK, 0);

  #ifdef DOTSTAR_PIN_PWR
  esp_rom_gpio_pad_select_gpio(DOTSTAR_PIN_PWR);
  gpio_ll_input_disable(&GPIO, DOTSTAR_PIN_PWR);
  gpio_ll_output_enable(&GPIO, DOTSTAR_PIN_PWR);
  gpio_ll_set_level(&GPIO, DOTSTAR_PIN_PWR, DOTSTAR_POWER_STATE);
  #endif

  board_dotstar_set(DOTSTAR_PIN_DATA, DOTSTAR_PIN_SCK, RGB_DOUBLE_TAP);
#endif

#ifdef LED_PIN
  esp_rom_gpio_pad_select_gpio(LED_PIN);
  gpio_ll_input_disable(&GPIO, LED_PIN);
  gpio_ll_output_enable(&GPIO, LED_PIN);

  gpio_ll_set_level(&GPIO, LED_PIN, LED_STATE_ON);
#endif
}

static void board_led_off(void) {
#ifdef NEOPIXEL_PIN
  board_neopixel_set(NEOPIXEL_PIN, RGB_OFF);

  // Neopixel reset time
  delay_cycle( NEOPIXEL_RESET_DELAY ) ;

  // TODO how to de-select GPIO pad to set it back to default state !?
  gpio_ll_output_disable(&GPIO, NEOPIXEL_PIN);

  #ifdef TCA9554_ADDR
  sw_i2c_begin(TCA9554_ADDR << 1);
  sw_i2c_write_byte(TCA9554_OUTPUT_PORT_REG);
  sw_i2c_write_byte(TCA9554_PERI_POWER_OFF_VALUE);
  sw_i2c_end();
  gpio_ll_output_disable(&GPIO, I2C_MASTER_SCL_IO);
  gpio_ll_output_disable(&GPIO, I2C_MASTER_SDA_IO);
  #endif

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
