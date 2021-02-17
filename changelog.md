# TinyUF2 Changelog

## 0.3.0 - 2021.02.17

- Add compiled date to INFO_UF2.TXT
- Add new port STM32F3

### ESP32-S2

- Add new boards: gravitech_cucumberRIS_v1.1, lilygo_ttgo_t8_s2_st7789, olimex_esp32s2_devkit_lipo_vB1

### iMXRT

- Fix FCFB address on RT1060
- Use LPGPR for double tap detection instead of generic sram.
- Fix flash-pyocd for imxrt evk board.

### LPC55

- No major changes

### STM32F3

- new port with stm32f303 discovery board

### STM32F4

- No major changes

## 0.2.1 - 2021.02.02

- Added stm32f401 blackpill
- Fix stm32f4 uart logging
- `update-*.uf2` is uploaded separately in release assests.

## 0.2.0 - 2021.01.19

- Add new port for NXP LPC55xx.
- Rename `USE_` feature to `TINYUF2_`

### ESP32-S2

- Add support for 1.14 ST7789 TFT
- New board: Adafruit Feather ESP32-S2 with and without TFT

### iMXRT

- Enhance iMXRT port by running entire bootloader on SRAM. Also support bootROM Serial Download Mode (BOOT_MODE = 01).
- Add port's readme

### LPC55

- Support Neopixel, double reset, flashing.
- New boards: LPCXpresso 55s68 and 55s28, Steiert's Feather Double M33

### STM32F4

- No major changes

## 0.1.0 - 2020.12.23

- Initial release with support for ESP32-S2, iMXRT 10xx, STM32F4
