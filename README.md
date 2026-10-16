# TinyUF2 Bootloader

[![License](https://img.shields.io/badge/license-MIT-brightgreen.svg)](https://opensource.org/licenses/MIT)[![Build Status](https://github.com/adafruit/tinyuf2/workflows/Build/badge.svg)](https://github.com/adafruit/tinyuf2/actions)![CodeRabbit Pull Request Reviews](https://img.shields.io/coderabbit/prs/github/adafruit/tinyuf2?utm_source=oss&utm_medium=github&utm_campaign=adafruit%2Ftinyuf2&labelColor=171717&color=FF570A&link=https%3A%2F%2Fcoderabbit.ai&label=CodeRabbit+Reviews)[![Greptile: The War on Bugs](https://www.greptile.com/badge.svg)](https://www.greptile.com/?utm_source=oss_badge&utm_medium=readme&utm_campaign=greptile_for_open_source)

This repo is cross-platform UF2 Bootloader projects for MCUs based on [TinyUSB](https://github.com/hathach/tinyusb)

```
.
├── apps              # Useful applications such as self-update, erase firmware
├── lib               # Sources from 3rd party such as tinyusb, mcu drivers ...
├── ports             # Port/family specific sources
│   ├── espressif
│   │   └── boards/   # Board specific sources
│   │   └── Makefile  # Makefile for this port
│   └── mimxrt10xx
├── src               # Cross-platform bootloader sources files
```

## Features

Supported features are

- Double tap to enter DFU, reboot to DFU and quick reboot from application
- DFU with MassStorage (MSC)
- Self update with uf2 file
- Indicator: LED, RGB, TFT
- Debug log with uart/swd

Not all features are implemented for all MCUs, following is supported MCUs and its feature

| MCU         | MSC  | Double Reset | Self-update | Write Protection | Neopixel | TFT  |
|:------------| :--: | :----------: |:-----------:| :--------------: |:--------:| :--: |
| ESP32 S2/S3 |  ✔   |   Need RC    |      ✔      |                  |    ✔     |  ✔   |
| K32L2       |  ✔   |      ✔       |             |                  |          |      |
| LPC55       |  ✔   |      ✔       |             |                  |    ✔     |      |
| iMXRT       |  ✔   |      ✔       |      ✔      |                  |    ✔     |      |
| SAMD51      |  ✔   |              |      ✔      |        ✔         |    ✔     |      |
| STM32F3     |  ✔   |      ✔       |      ✔      |        ✔         |    ✔     |      |
| STM32F4     |  ✔   |      ✔       |      ✔      |        ✔         |    ✔     |      |
| STM32H5     |  ✔   |      ✔       |      ✔      |        ✔         |          |      |

## Supported MCUs and Boards

Please refer to [supported boards](./supported_boards.md) for the complete list of supported MCUs and boards.

## Build and Flash

Following is generic compiling information. Each port may require extra set-up and slight different process e.g esp32s2
require ESP-IDF.

### Clone

Clone this repo with its submodule

```
git clone git@github.com:adafruit/tinyuf2.git tinyuf2
cd tinyuf2
git submodule update --init
```

### Compile

Firstly we need to get all submodule dependency for our board using `tools/get_deps.py` script with either family input or using --board option. You only need to do this once for each family

```
python tools/get_deps.py stm32f4
python tools/get_deps.py --board feather_stm32f405_express
```

To build this for a specific board, we need to change current directory to its port folder

```
cd ports/stm32f4
```

Then compile with `all` target:

```
make BOARD=feather_stm32f405_express all
```

Every port also builds with CMake, the way CI builds it (Espressif uses ESP-IDF's, see its README):

```
cmake -B build -G Ninja -DBOARD=feather_stm32f405_express ports/stm32f4
cmake --build build
```

The bootloader images land in `ports/<port>/_bin/<board>`. Each application the port supports (self-update, blinky, ...) is built as its own CMake project in `build/apps/<app>`, its UF2 in `_bin/<board>/apps`. Flash with targets such as `tinyuf2-jlink`, `tinyuf2-stlink` or `<app>-uf2`.

### Flash

`flash` target will use the default on-board debugger (jlink/cmsisdap/stlink/dfu) to flash the binary, please install those support software in advance. Some board use bootloader/DFU via serial which is required to pass to make command

```
make BOARD=feather_stm32f405_express flash
```

If you use an external debugger, there is `flash-jlink`, `flash-stlink`, `flash-pyocd` which are mostly like to work out of the box for most of the supported board.

### Debug

To compile for debugging add `DEBUG=1`, this will mostly change the compiler optimization

```
make BOARD=feather_stm32f405_express DEBUG=1 all
```

#### Log

Should you have an issue running example and/or submitting an bug report. You could enable TinyUSB built-in debug logging with optional `LOG=`.
- **LOG=1** will print message from bootloader and error if any from TinyUSB stack.
- **LOG=2** and **LOG=3** will print more information with TinyUSB stack events

```
make BOARD=feather_stm32f405_express LOG=1 all
```

#### Logger

By default log message is printed via on-board UART which is slow and take lots of CPU time comparing to USB speed. If your board support on-board/external debugger, it would be more efficient to use it for logging. There are 2 protocols:

- `LOGGER=rtt`: use [Segger RTT protocol](https://www.segger.com/products/debug-probes/j-link/technology/about-real-time-transfer/)
  - Cons: requires jlink as the debugger.
  - Pros: work with most if not all MCUs
  - Software viewer is JLink RTT Viewer/Client/Logger which is bundled with JLink driver package.

```
make BOARD=feather_stm32f405_express LOG=2 LOGGER=rtt all
```
