# TinyUF2 Changelog

## 0.6.0

### ESP32-S2

- Update IDF to release/v4.4
- Improve Adafruit Feather ESP32S2, Espressif HMI, Micro S2,  board
- Add new boards: Adafruit QTPY S2, Lolin S2 pico

### STM32F4

- fix board_flash_write() on stm32f4

## 0.5.2

Added new boards: MorphESP-240 ESP32S2, Lolin S2 Mini, Espressif HMI devkit

## 0.5.1

### ESP32-S2

- Added new board: unexpectedmaker_feathers2_neo

### STM32F4

- fix updating issue with circuipython

## 0.5.0

- Update self-update as application

### ESP32-S2

- Update IDF to v4.3
- Add new boards: muselab_nanoesp32_s2, atmegazero_esp32s2
- Fix esp32s2 request to uf2 using reset hint

### iMXRT

- self-install tinyuf2 when FCFB not valid
- Use official nxp mcux-sdk submodule
- Refactor fsl_romapi
- Add support for on-chip flash (W25Q32JV) for rt1024 and rt1064

### LPC55

- Use official nxp mcux-sdk submodule

## 0.4.0

- Add support for multiple sectors per cluster in GhostFAT to enable larger flash sizes
  - Add native test for ghostfat with varous checks
- Add new board API:
  - board_reset()
  - board_flash_erase_app()
  - board_usb_init()
  - board_uart_init()
- Add `erase_firmware` application target (only implemented for iMXRT for now).
  - TinyUF2 will erase whole flash if `MAGIC_ERASE_APP` is written by application.
  - `erase_firmware.uf2` is also uploaded as part of build/release asset if available
- No major chagnes to LPC55, STM32 F3 F4

### ESP32-S2

- Rework Dotstar driver
- Speed up flashing speed by increase cache size to 64KB and using block erase
- Add new boards:
  - Adafruit Fun House
  - Unexpected Maker TinyS2

### iMXRT

- Always write tinyuf2 image to flash if loaded in Serial Donwload mode (Boot Mode = 01)
- Add `erase_firmware.uf2` to erase the whole flash except bootloader
- Add sdphost binary for arm 32bit e.g raspberry pi 4
- Add `esp32programmer.uf2` app for selected board.

## 0.3.0

- Add compiled date to INFO_UF2.TXT
- Add new port STM32F3

### ESP32-S2

- Add new boards: gravitech_cucumberRIS_v1.1, lilygo_ttgo_t8_s2_st7789, olimex_esp32s2_devkit_lipo_vB1, artisense_rd00

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

## 0.2.1

- Added stm32f401 blackpill
- Fix stm32f4 uart logging
- `update-*.uf2` is uploaded separately in release assests.

## 0.2.0

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

## 0.1.0

- Initial release with support for ESP32-S2, iMXRT 10xx, STM32F4
