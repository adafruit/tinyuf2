/*
 * SPDX-FileCopyrightText: 2019-2025 Espressif Systems (Shanghai) CO LTD
 * SPDX-FileCopyrightText: 2026 Adafruit Industries
 * SPDX-License-Identifier: Apache-2.0
 *
 * ADC setup and calibration follow ESP-IDF v5.4.3 adc_oneshot_hal.c,
 * adc_cali_curve_fitting.c, and esp32p4/esp_efuse_rtc_calib.c.
 */

#include "sdkconfig.h"
#include "board.h"
#include "double_reset_adc.h"

#ifdef PIN_DOUBLE_RESET_ADC

#if !CONFIG_IDF_TARGET_ESP32P4
#error "ADC double-reset detection currently supports ESP32-P4 only"
#endif

#include <stdint.h>
#include "esp_efuse_rtc_calib.h"
#include "esp_log.h"
#include "esp_private/regi2c_ctrl.h"
#include "esp_rom_gpio.h"
#include "esp_rom_sys.h"
#include "hal/adc_ll.h"
#include "hal/gpio_ll.h"
#include "soc/gpio_sig_map.h"
#include "soc/pmu_reg.h"

#define ADC_SAMPLE_COUNT 8
#define ADC_TIMEOUT_US 1000
#define ADC_DISCHARGE_US 5000

_Static_assert(BOARD_DOUBLE_RESET_ADC_CHANNEL >= 0 &&
               BOARD_DOUBLE_RESET_ADC_CHANNEL < SOC_ADC_CHANNEL_NUM(ADC_UNIT_1),
               "Double-reset pin must use ADC1");
_Static_assert(PIN_DOUBLE_RESET_ADC == 16 + BOARD_DOUBLE_RESET_ADC_CHANNEL,
               "Double-reset GPIO does not match its ESP32-P4 ADC1 channel");

static const char *TAG = "double_reset_adc";

static void pin_float(void) {
  gpio_ll_output_disable(&GPIO, PIN_DOUBLE_RESET_ADC);
  gpio_ll_input_disable(&GPIO, PIN_DOUBLE_RESET_ADC);
  gpio_ll_pullup_dis(&GPIO, PIN_DOUBLE_RESET_ADC);
  gpio_ll_pulldown_dis(&GPIO, PIN_DOUBLE_RESET_ADC);
  gpio_ll_sleep_sel_dis(&GPIO, PIN_DOUBLE_RESET_ADC);
  gpio_ll_func_sel(&GPIO, PIN_DOUBLE_RESET_ADC, PIN_FUNC_GPIO);
}

static bool adc_read(uint32_t *raw) {
  adc_oneshot_ll_start(ADC_UNIT_1);
  // Let the new start reach the RTC controller before checking its DONE bit.
  esp_rom_delay_us(10);
  for (uint32_t waited = 0; waited < ADC_TIMEOUT_US; waited++) {
    if (adc_oneshot_ll_get_event(ADC_LL_EVENT_ADC1_ONESHOT_DONE)) {
      *raw = adc_oneshot_ll_get_raw_result(ADC_UNIT_1);
      return true;
    }
    esp_rom_delay_us(1);
  }
  return false;
}

bool double_reset_adc_detect(void) {
  pin_float();

  int version = esp_efuse_rtc_calib_get_ver();
  if (version < ESP_EFUSE_ADC_CALIB_VER_MIN || version > ESP_EFUSE_ADC_CALIB_VER_MAX) {
    ESP_LOGW(TAG, "ADC calibration unavailable; use the BOOT button");
    return false;
  }

  uint32_t reference_raw = 0;
  uint32_t reference_mv = 0;
  if (esp_efuse_rtc_calib_get_cal_voltage(version, ADC_UNIT_1, ADC_ATTEN_DB_12,
                                        &reference_raw, &reference_mv) != ESP_OK ||
      reference_raw == 0 || reference_raw > 4095 || reference_mv != 2300) {
    ESP_LOGW(TAG, "Invalid ADC voltage calibration; use the BOOT button");
    return false;
  }
  uint32_t init_code = esp_efuse_rtc_calib_get_init_code(version, ADC_UNIT_1, ADC_ATTEN_DB_12);
  if (init_code == 0 || init_code > 4095) {
    ESP_LOGW(TAG, "Invalid ADC offset calibration; use the BOOT button");
    return false;
  }
  int compensation = esp_efuse_rtc_calib_get_chan_compens(
      version, ADC_UNIT_1, BOARD_DOUBLE_RESET_ADC_CHANNEL, ADC_ATTEN_DB_12);

  // The second-stage bootloader already uses ADC1 for entropy. Preserve that
  // configuration while temporarily disconnecting its internal noise source.
  uint32_t saved_adc_ctrl = ADC.ctrl_reg.val;
  uint32_t saved_adc_ctrl2 = ADC.ctrl2.val;
  uint32_t saved_lp_clock = LPPERI.clk_en.val;
  uint32_t saved_lp_power = LP_ADC.force_wpd_sar.val;
  uint32_t saved_reader = LP_ADC.reader1_ctrl.val;
  uint32_t saved_mux = LP_ADC.meas1_mux.val;
  uint32_t saved_measurement = LP_ADC.meas1_ctrl2.val;
  uint32_t saved_atten = LP_ADC.atten1.val;
  uint32_t saved_pmu = REG_READ(PMU_RF_PWC_REG);

  // Pause the digital controller before taking ownership of ADC1.
  adc_ll_digi_trigger_disable();
  esp_rom_delay_us(100);
  LPPERI.clk_en.ck_en_lp_i2cmst = 1;
  SET_PERI_REG_MASK(PMU_RF_PWC_REG, PMU_XPD_PERIF_I2C);

  uint8_t saved_init_low = REGI2C_READ(I2C_SAR_ADC, ADC_SAR1_INITIAL_CODE_LOW_ADDR);
  uint8_t saved_init_high = REGI2C_READ(I2C_SAR_ADC, ADC_SAR1_INITIAL_CODE_HIGH_ADDR);
  uint8_t saved_reference = REGI2C_READ(I2C_SAR_ADC, ADC_SAR1_DREF_ADDR);
  uint8_t saved_calibration = REGI2C_READ(I2C_SAR_ADC, ADC_SAR1_ENCAL_GND_ADDR);
  uint8_t saved_entropy = REGI2C_READ(I2C_SAR_ADC, I2C_SAR_ADC_ENT_VDD_GRP1);

  // IDF 6's RNG disable also changes ADC2, pattern and clock state. Only clear
  // these saved analog fields, leaving that unrelated configuration untouched.
  REGI2C_WRITE_MASK(I2C_SAR_ADC, I2C_SAR_ADC_ENT_VDD_GRP1, 0);
  REGI2C_WRITE_MASK(I2C_SAR_ADC, I2C_SAR_ADC_DTEST_VDD_GRP1, 0);
  adc_ll_set_power_manage(ADC_UNIT_1, ADC_LL_POWER_SW_ON);
  adc_ll_set_sar_clk_div(ADC_UNIT_1, ADC_LL_SAR_CLK_DIV_DEFAULT(ADC_UNIT_1));
  adc_oneshot_ll_output_invert(ADC_UNIT_1, false);
  adc_oneshot_ll_set_atten(ADC_UNIT_1, BOARD_DOUBLE_RESET_ADC_CHANNEL, ADC_ATTEN_DB_12);
  adc_oneshot_ll_set_output_bits(ADC_UNIT_1, ADC_BITWIDTH_12);
  adc_oneshot_ll_set_channel(ADC_UNIT_1, BOARD_DOUBLE_RESET_ADC_CHANNEL);
  adc_ll_set_controller(ADC_UNIT_1, ADC_LL_CTRL_RTC);
  adc_ll_calibration_init(ADC_UNIT_1);
  adc_ll_calibration_finish(ADC_UNIT_1);
  adc_ll_set_calibration_param(ADC_UNIT_1, init_code);
  esp_rom_delay_us(100);

  uint32_t raw = 0;
  uint32_t total = 0;
  bool valid = adc_read(&raw); // Discard the first conversion after switching.
  for (unsigned int i = 0; valid && i < ADC_SAMPLE_COUNT; i++) {
    valid = adc_read(&raw);
    total += raw;
  }

  // P4's adc_oneshot_ll_disable_all_unit() is a no-op. Stop the RTC start
  // explicitly, then restore the entropy source, with its timer restored last.
  LP_ADC.meas1_ctrl2.meas1_start_sar = 0;
  adc_oneshot_ll_disable_channel(ADC_UNIT_1);
  REGI2C_WRITE(I2C_SAR_ADC, ADC_SAR1_INITIAL_CODE_LOW_ADDR, saved_init_low);
  REGI2C_WRITE(I2C_SAR_ADC, ADC_SAR1_INITIAL_CODE_HIGH_ADDR, saved_init_high);
  REGI2C_WRITE(I2C_SAR_ADC, ADC_SAR1_DREF_ADDR, saved_reference);
  REGI2C_WRITE(I2C_SAR_ADC, ADC_SAR1_ENCAL_GND_ADDR, saved_calibration);
  REGI2C_WRITE(I2C_SAR_ADC, I2C_SAR_ADC_ENT_VDD_GRP1, saved_entropy);
  LP_ADC.meas1_mux.val = saved_mux;
  LP_ADC.meas1_ctrl2.val = saved_measurement;
  LP_ADC.reader1_ctrl.val = saved_reader;
  LP_ADC.atten1.val = saved_atten;
  LP_ADC.force_wpd_sar.val = saved_lp_power;
  ADC.ctrl_reg.val = saved_adc_ctrl;
  REG_WRITE(PMU_RF_PWC_REG, saved_pmu);
  LPPERI.clk_en.val = saved_lp_clock;
  ADC.ctrl2.val = saved_adc_ctrl2;

  if (!valid) {
    ESP_LOGW(TAG, "ADC conversion timed out; use the BOOT button");
    return false;
  }

  // First-stage eFuse voltage calibration, including channel compensation.
  // P4 ADC1/12 dB's further curve correction is below 1 mV near 2500 mV;
  // this marker comparator does not require the full application ADC driver.
  int64_t corrected_total = (int64_t)total - (int64_t)compensation * ADC_SAMPLE_COUNT;
  return corrected_total * reference_mv >
         (int64_t)BOARD_DOUBLE_RESET_ADC_THRESHOLD_MV * reference_raw * ADC_SAMPLE_COUNT;
}

static void pin_drive(bool high) {
  pin_float();
  gpio_ll_od_disable(&GPIO, PIN_DOUBLE_RESET_ADC);
  esp_rom_gpio_connect_out_signal(PIN_DOUBLE_RESET_ADC, SIG_GPIO_OUT_IDX, false, false);
  gpio_ll_set_level(&GPIO, PIN_DOUBLE_RESET_ADC, high);
  gpio_ll_output_enable(&GPIO, PIN_DOUBLE_RESET_ADC);
}

void double_reset_adc_arm(void) {
  pin_drive(true);
}

void double_reset_adc_clear(void) {
  pin_drive(false);
  esp_rom_delay_us(ADC_DISCHARGE_US);
  pin_float();
}

#endif // PIN_DOUBLE_RESET_ADC
