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
│   │   └── CMakeLists.txt  # CMake project for this port
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

Then build a board from the repository root with CMake, the way CI builds it (Espressif uses ESP-IDF's `idf.py`, see
[its README](ports/espressif/README.md)):

```
cmake -B build -G Ninja -DBOARD=feather_stm32f405_express ports/stm32f4
cmake --build build
```

The bootloader images land in `ports/<port>/_bin/<board>` (`-DARTIFACT_PATH=<dir>` puts them elsewhere). Each
application the port supports (self-update, blinky, ...) is built as its own CMake project in `build/apps/<app>`, its
UF2 in `_bin/<board>/apps`.

### Flash

Each port adds a flash target for each tool it supports; install the tool first, then build the target. For example
feather_stm32f405_express through the STM32 ROM DFU bootloader:

```
cmake --build build --target tinyuf2-dfu-util
```

| Target             | Tool                                          | Ports                                                    |
|--------------------|-----------------------------------------------|----------------------------------------------------------|
| `tinyuf2-jlink`    | J-Link `JLinkExe`                             | boards whose `board.cmake` sets `JLINK_DEVICE`           |
| `tinyuf2-stlink`   | `STM32_Programmer_CLI`                        | stm32f3, stm32f4, stm32h5, stm32h7, stm32l4              |
| `tinyuf2-pyocd`    | pyOCD                                         | kinetis_k32l2, lpc55, mimxrt10xx                         |
| `tinyuf2-dfu-util` | dfu-util to the STM32 ROM DFU bootloader      | stm32f4, stm32h5, stm32l4                                |
| `tinyuf2-openocd`  | OpenOCD                                       | ch32v20x (WCH's fork), maxim (ADI's)                     |
| `tinyuf2-sdp`      | `sdphost`/`blhost` to the i.MX RT ROM         | mimxrt10xx, see [its README](ports/mimxrt10xx/README.md) |
| `tinyuf2-teensy`   | `teensy_loader_cli`                           | teensy40, teensy41                                       |
| `<app>-uf2`        | `uf2conv.py --deploy` to the bootloader drive | each application the port builds                         |

There are no erase targets: erase with the tool's own command for your chip.

### Debug

To compile for debugging configure with `-DCMAKE_BUILD_TYPE=Debug`, this will mostly change the compiler optimization
(`-Og` in place of the default MinSizeRel's `-Os`)

```
cmake -B build -G Ninja -DBOARD=feather_stm32f405_express -DCMAKE_BUILD_TYPE=Debug ports/stm32f4
cmake --build build
```

#### Log

Should you have an issue running example and/or submitting an bug report. You could enable TinyUSB built-in debug logging with optional `-DLOG=`.
- **LOG=1** will print message from bootloader and error if any from TinyUSB stack.
- **LOG=2** and **LOG=3** will print more information with TinyUSB stack events

```
cmake -B build -G Ninja -DBOARD=feather_stm32f405_express -DCMAKE_BUILD_TYPE=MinSizeRel -DLOG=1 ports/stm32f4
cmake --build build
```

#### Logger

By default log message is printed via on-board UART which is slow and take lots of CPU time comparing to USB speed. If your board support on-board/external debugger, it would be more efficient to use it for logging. There are 2 protocols:

- `-DLOGGER=RTT`: use [Segger RTT protocol](https://www.segger.com/products/debug-probes/j-link/technology/about-real-time-transfer/)
  - Cons: requires jlink as the debugger.
  - Pros: work with most if not all MCUs
  - Software viewer is JLink RTT Viewer/Client/Logger which is bundled with JLink driver package.

```
cmake -B build -G Ninja -DBOARD=feather_stm32f405_express -DCMAKE_BUILD_TYPE=MinSizeRel -DLOG=2 -DLOGGER=RTT ports/stm32f4
cmake --build build
```
