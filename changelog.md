# TinyUF2 Changelog

## 0.2.1 - 2021.01.19

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
