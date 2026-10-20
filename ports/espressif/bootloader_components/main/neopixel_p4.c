/*
 * SPDX-FileCopyrightText: 2019-2025 Espressif Systems (Shanghai) CO LTD
 * SPDX-FileCopyrightText: 2026 Adafruit Industries
 * SPDX-License-Identifier: Apache-2.0
 *
 * Based on ESP-IDF v5.4.3 hal/rmt_hal.c and esp_driver_rmt/src/rmt_private.h.
 * WS2812 pulse durations from led_strip 2.x led_strip_rmt_encoder.c.
 */

#include "neopixel_p4.h"
#include "esp_rom_gpio.h"
#include "esp_rom_sys.h"
#include "hal/gpio_ll.h"
#include "hal/rmt_ll.h"
#include "soc/gpio_sig_map.h"
#include "soc/soc_caps.h"

// The hardware memory symbol is supplied by esp32p4.peripherals.ld.
typedef struct {
  struct {
    rmt_symbol_word_t symbols[SOC_RMT_MEM_WORDS_PER_CHANNEL];
  } channels[RMT_LL_GET(CHANS_PER_INST)];
} bootloader_rmt_mem_t;
extern bootloader_rmt_mem_t RMTMEM;

bool bootloader_neopixel_write(uint32_t pin, const uint8_t *grb, size_t count) {
  // One pixel plus the terminating symbol fits entirely in channel 0 memory.
  if (!grb || count != 3 || pin >= SOC_GPIO_PIN_COUNT) {
    return false;
  }

  gpio_ll_set_level(&GPIO, pin, 0);
  gpio_ll_func_sel(&GPIO, pin, PIN_FUNC_GPIO);
  gpio_ll_input_disable(&GPIO, pin);
  gpio_ll_od_disable(&GPIO, pin);
  esp_rom_gpio_connect_out_signal(pin, SIG_GPIO_OUT_IDX, false, false);
  gpio_ll_output_enable(&GPIO, pin);
  esp_rom_delay_us(300);

  // No scheduler or interrupt-driven RMT users exist in the second stage.
  const int __DECLARE_RCC_ATOMIC_ENV = 0;
  bool saved_bus_clock = HP_SYS_CLKRST.soc_clk_ctrl2.reg_rmt_sys_clk_en;
  uint32_t saved_clock = HP_SYS_CLKRST.peri_clk_ctrl22.val;
  rmt_ll_enable_bus_clock(0, true);
  rmt_ll_reset_register(0);
  // IDF 6 removed rmt_ll_enable_periph_clock; retain its hardware settings.
  RMT.sys_conf.clk_en = 1;
  RMT.sys_conf.mem_clk_force_on = 1;
  rmt_ll_mem_force_power_on(&RMT);
  rmt_ll_enable_mem_access_nonfifo(&RMT, true);
  rmt_ll_enable_interrupt(&RMT, UINT32_MAX, false);
  rmt_ll_clear_interrupt_status(&RMT, UINT32_MAX);

  // 40 MHz XTAL / 1 group divider / 4 channel divider = 10 MHz.
  rmt_ll_set_group_clock_src(&RMT, 0, RMT_CLK_SRC_XTAL, 1, 0, 0);
  rmt_ll_enable_group_clock(&RMT, true);
  rmt_ll_tx_set_channel_clock_div(&RMT, 0, 4);
  rmt_ll_tx_set_mem_blocks(&RMT, 0, 1);
  rmt_ll_tx_enable_carrier_modulation(&RMT, 0, false);
  rmt_ll_tx_enable_wrap(&RMT, 0, false);
  rmt_ll_tx_enable_loop(&RMT, 0, false);
  rmt_ll_tx_fix_idle_level(&RMT, 0, 0, true);
  rmt_ll_tx_reset_channels_clock_div(&RMT, 1);
  rmt_ll_tx_reset_pointer(&RMT, 0);

  volatile rmt_symbol_word_t *symbols = RMTMEM.channels[0].symbols;
  size_t index = 0;
  for (size_t byte = 0; byte < count; byte++) {
    for (uint8_t mask = 0x80; mask; mask >>= 1) {
      // HIGH then LOW: 0 = 0.3/0.9 us; 1 = 0.9/0.3 us, MSB first.
      symbols[index++].val = (grb[byte] & mask) ?
                            (9 | (1 << 15) | (3 << 16)) :
                            (3 | (1 << 15) | (9 << 16));
    }
  }
  symbols[index].val = 0; // A zero duration terminates transmission.

  esp_rom_gpio_connect_out_signal(pin, RMT_SIG_PAD_OUT0_IDX, false, false);
  rmt_ll_tx_start(&RMT, 0);
  bool done = false;
  for (unsigned int waited = 0; waited < 1000; waited++) {
    uint32_t status = rmt_ll_tx_get_interrupt_status_raw(&RMT, 0);
    if (status & RMT_LL_EVENT_TX_ERROR(0)) {
      break;
    }
    if (status & RMT_LL_EVENT_TX_DONE(0)) {
      done = true;
      break;
    }
    esp_rom_delay_us(1);
  }

  rmt_ll_tx_stop(&RMT, 0);
  // Disconnect the peripheral before resetting it; latch the pixel at LOW.
  esp_rom_gpio_connect_out_signal(pin, SIG_GPIO_OUT_IDX, false, false);
  gpio_ll_set_level(&GPIO, pin, 0);
  gpio_ll_output_enable(&GPIO, pin);
  esp_rom_delay_us(300);
  rmt_ll_reset_register(0);
  rmt_ll_mem_power_by_pmu(&RMT);
  RMT.sys_conf.clk_en = 0;
  RMT.sys_conf.mem_clk_force_on = 0;
  HP_SYS_CLKRST.peri_clk_ctrl22.val = saved_clock;
  rmt_ll_enable_bus_clock(0, saved_bus_clock);
  return done;
}
