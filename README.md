# TinyUF2 Bootloader

[![Build Status](https://github.com/adafruit/tinyuf2/workflows/Build/badge.svg)](https://github.com/adafruit/tinyuf2/actions)[![License](https://img.shields.io/badge/license-MIT-brightgreen.svg)](https://opensource.org/licenses/MIT)

This repo is cross-platform UF2 Bootloader projects for MCUs based on [TinyUSB](https://github.com/hathach/tinyusb)

```
.
├── apps              # Useful applications such as self-update, erase firmware
├── lib               # Sources from 3rd party such as tinyusb, mcu drivers ...
├── ports             # Port/family specific sources
│   ├── esp32s2       
│   │   └── boards/   # Board specific sources
│   │   └── Makefile  # Makefile for this port
│   └── mimxrt10xx         
├── src               # Cross-platform bootloader sources files
```

## Features

TODO more docs later

- Support ESP32-S2, iMXRT10xx, LPC55xx, STM32F3, STM32F4
- Self update with update file in uf2 format
- Indicator: LED, RGB
- Debug log with uart/swd
- Double tap to enter DFU, reboot to DFU and quick reboot from application

## Build and Flash

### Requirements

- GCC cross compiler and Make

### Compile

Firstly clone this repo and its submodules with 

```
$ git clone --recurse-submodules https://github.com/Franzininho/tinyuf2.git
```

To build this for a specific board, we need to change current directory to its port folder

```
$ cd ports/stm32f4
```

Then compile with `make BOARD=[board_name] all`, for example

```
make BOARD=feather_stm32f405_express all
```

### Flash

`flash` target will use the default on-board debugger (jlink/cmsisdap/stlink/dfu) to flash the binary, please install those support software in advance. Some board use bootloader/DFU via serial which is required to pass to make command

```
$ make BOARD=feather_stm32f405_express flash
```

If you use an external debugger, there is `flash-jlink`, `flash-stlink`, `flash-pyocd` which are mostly like to work out of the box for most of the supported board.

### Debug

To compile for debugging add `DEBUG=1`, this will mostly change the compiler optimization

```
$ make BOARD=feather_stm32f405_express DEBUG=1 all
```

#### Log

Should you have an issue running example and/or submitting an bug report. You could enable TinyUSB built-in debug logging with optional `LOG=`. LOG=1 will print out only message from bootloader project, while LOG=2 print more information with TinyUSB stack information events as well (note: it is quite a bit). LOG=3 or higher is not used yet. 

```
$ make BOARD=feather_stm32f405_express LOG=1 all
```

#### Logger

By default log message is printed via on-board UART which is slow and take lots of CPU time comparing to USB speed. If your board support on-board/external debugger, it would be more efficient to use it for logging. There are 2 protocols: 

- `LOGGER=rtt`: use [Segger RTT protocol](https://www.segger.com/products/debug-probes/j-link/technology/about-real-time-transfer/)
  - Cons: requires jlink as the debugger.
  - Pros: work with most if not all MCUs
  - Software viewer is JLink RTT Viewer/Client/Logger which is bundled with JLink driver package.
- `LOGGER=swo`: Use dedicated SWO pin of ARM Cortex SWD debug header.
  - Cons: only work with ARM Cortex MCUs minus M0
  - Pros: should be compatible with more debugger that support SWO.
  - Software viewer should be provided along with your debugger driver.

```
$ make BOARD=feather_stm32f405_express LOG=2 LOGGER=rtt all
$ make BOARD=feather_stm32f405_express LOG=2 LOGGER=swo all
```
