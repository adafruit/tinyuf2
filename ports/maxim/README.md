# TinyUF2 - MAX32690 Port

This folder contains the port of TinyUF2 for Analog Devices' MAX32xxx/MAX78000 MCUs.

## Navigation

- [Requirements](#requirements)
  - [Requirements for Linux/macOS (Generic)](#requirements-for-linuxmacos-generic)
  - [Requirements for Windows (Using MSDK — Optional)](#requirements-for-windows-using-msdk--optional)
- [MSDK Windows Environment Setup](#msdk-windows-environment-setup)
- [Available Boards](#available-boards)
- [Building the Bootloader](#building-the-bootloader)
- [Building Demo Applications](#building-demo-applications)
  - [To Build Individual Applications](#to-build-individual-applications)
  - [To Clean Individual Applications](#to-clean-individual-applications)
- [Flashing the Bootloader](#flashing-the-bootloader)
  - [J-Link vs OpenOCD](#j-link-vs-openocd)
  - [Flashing with J-Link](#1-j-link-default)
  - [Flashing with OpenOCD (MSDK)](#2-openocd-from-msdk-optional)
- [Flashing Example Applications](#flashing-example-applications)
  - [Flashing via Drag-and-Drop](#flashing-via-drag-and-drop)
  - [Re-Entering Bootloader Mode](#re-entering-bootloader-mode)
- [Port Directory Structure](#port-directory-structure)


## Requirements

This guide focuses on building TinyUF2 for Analog Devices' MAX32 parts.
It is written with Windows users in mind using the **MSDK**, but TinyUF2 is fully portable and can be built with a standard toolchain on Linux and macOS.


### Requirements for Linux/macOS (Generic)

You do **not** need the MSDK to build TinyUF2 on Linux or macOS.
All you need is a basic toolchain:

- **GNU ARM Toolchain** (`arm-none-eabi-gcc`) available in your `PATH`
- **make**
- **CMake**
- **git** (required for submodules)
- **SDK Dependencies**

### Installing SDK Dependencies
```bash
python tools/get_deps.py maxim
```
or
```bash
python tools/get_deps.py --board apard32690
```


#### macOS Dependency Install
```bash
brew install arm-none-eabi-gcc make cmake git
```

#### Ubuntu Dependency Install
```bash
sudo apt update
sudo apt install gcc-arm-none-eabi make cmake git
```

---

### Requirements for Windows (Using MSDK — Optional)

If you're using Analog Devices' [MSDK](https://github.com/analogdevicesinc/msdk), it includes:

- Pre-configured **GNU ARM Toolchain**
- **MSYS2** terminal environment
- Optional **OpenOCD** with MAX32 flash support

Download MSDK from:
[Analog Devices Embedded Software Center (MaximSDK)](https://www.analog.com/en/resources/evaluation-hardware-and-software/embedded-development-software/software-download.html?swpart=SFW0010820B)

You will need:

- ARM GNU Toolchain (`arm-none-eabi-gcc`) — *included with MSDK*
- `make`:
  - MSDK MSYS2: `C:/MaximSDK/Tools/MSYS2/usr/bin/make.exe`
  - System-wide MSYS2: `C:/msys64/usr/bin/make.exe`
- `git` (may need to be installed inside MSYS2):
  ```bash
  pacman -S git
  ```

If needed, set `MAXIM_PATH` to point to your MSDK installation:

```bash
export MAXIM_PATH=/c/MaximSDK
```

## MSDK (Windows) Environment Setup

### 1. Using MSDK's MSYS2

Open MSYS2 (`mingw32.exe` or `mingw64.exe`) from:

```
C:/MaximSDK/Tools/MSYS2/
```

No further setup is needed — the required ARM toolchain should be available.

### 2. Using a System-wide MSYS2 or mingw (Alternative)

If you are using your own MSYS2 or mingw installation (not MSDK’s MSYS2), you must manually add the MSDK's GNUTools to your PATH before building:

```bash
export PATH="/c/MaximSDK/Tools/GNUTools/10.3/bin/:$PATH"
```

(Adjust the path if your MSDK installation is in a different location.)

## Available Boards

Each port supports multiple hardware platforms.
The specific boards available for each device can be found inside:

```
ports/maxim/boards/
```

For example:

```
tinyuf2/ports/maxim/boards/
    apard32690
    max32650evkit
    max32650fthr
    max32666evkit
    max32666fthr
    max32690evkit
    max78002evkit
```

When initially configuring cmake, make sure to specify a valid `BOARD` name from the available list. Otherwise, the build will fail if an invalid board name is provided.

```bash
cmake -DBOARD=apard32690 ..
```

Afterward, all the cmake/cmake commands can be run within the `build` directory without needing to specify the board again, as it will be cached.

<br>

## Building the Bootloader and Applications

1. Open your MSYS2 terminal (preferably MSDK’s).
2. Navigate to the maxim folder, create a build directory, and change into it:

```bash
cd ports/maxim
mkdir build
cd build
```

3. Configure cmake with correct BOARD and run make to build:

```bash
cmake -DBOARD=apard32690 ..
make
```

It will build the TinyUF2 bootloader along with all supported application e.g blinky, update-tinyuf2, erase-firmware. Tinyuf2 binaries will appear in `build/` folder while application are created in `build/apps/$(APP)/`.

- **Blinky** (`apps/blinky`) is useful to quickly test the bootloader
- **Erase Firmware** (`apps/erase_firmware`) put the board into a clean state
- **Self-Update** (`apps/self_update`) allows updating the bootloader itself

To list all supported targets, run:

```bash
cmake --build . --target help

The following are some of the valid targets for this Makefile:
... all (the default if no target is provided)
... clean
... depend
... edit_cache
... rebuild_cache
... blinky-uf2
... erase_firmware-uf2
... tinyuf2-erase-jlink
... tinyuf2-jlink
... tinyuf2-openocd
... update-tinyuf2-uf2
... blinky
... board_max32666fthr
... erase_firmware
... tinyuf2
... update-tinyuf2
```

### To Build Individual Targets

To build a specific target, you can specify it directly with `make` or using `cmake --build`:

```bash
make blinky
cmake --build . --target blinky
```

<br>

## Flashing the Bootloader

### J-Link and OpenOCD

TinyUF2 supports two main ways to flash firmware:

- **J-Link**: Uses SEGGER's proprietary debug probe. Supports fast, reliable flashing and debugging over SWD or JTAG. Requires a J-Link device and SEGGER drivers.

- **OpenOCD (MSDK)**: Open-source tool for programming/debugging via CMSIS-DAP or other adapters.
  The MSDK includes a custom version of OpenOCD that supports MAX32 devices, since official OpenOCD does not yet have MAX32 flash algorithm support.

### 1. J-Link

To flash using a J-Link debugger:

```bash
make tinyuf2-jlink
```

To erase before flashing:

```bash
make tinyuf2-erase-jlink tinyuf2-jlink
```

### 2. OpenOCD from MSDK (optional)

If you prefer OpenOCD and you have it installed through MSDK:

```bash
make tinyuf2-openocd
```

CMake will automatically leverage the MAXIM_PATH system environment variable if
a MAXIM_PATH is not manually specified. To manually specify a MSDK path,
you can pass the MaximSDK directory's location to cmake when configuring the
build:

```bash
cmake -DBOARD=apard32690 -DMAXIM_PATH=/path/to/MaximSDK ..
```
or  after initial configuration (in the build directory):

```bash
cmake -DMAXIM_PATH=C:/MaximSDK .
```

## Flashing Example Applications

After building any of the demo applications (Blinky, Erase Firmware, or Self-Update), a UF2 file will be generated in:

```
build/apps/<application>/<application>.uf2
```

For example:

```
apps/blinky/blinky.uf2
```

### Flashing via Drag-and-Drop

1. **Enter bootloader mode** on your board:
   - Typically, perform a **double-tap on the reset button** within **500 milliseconds**.
   - The board will appear as a **USB mass storage device** (for example, named `3269BOOT`) in your operating system's **File Explorer** (Windows) or **Finder** (macOS) or **File Manager** (Linux).

2. **Using your file explorer**, locate the `.uf2` file you built, and **drag and drop** it onto the mounted TinyUF2 USB drive.

3. The board will automatically reboot and begin running the new application.

### Flashing using make/cmake

To flash an application using the command line, you can use the `make` or `cmake` command:

```bash
make blinky-uf2
cmake --build . --target blinky-uf2
```

### Re-Entering Bootloader Mode

To flash a different application or return to bootloader mode:

- Perform another **double-tap** of the reset button within 500 milliseconds.
- The board will reappear as a USB mass storage device for new UF2 flashing.

> ⚠️ **Note:**
> If double-tap reset does not work (for example, if the running application has corrupted necessary flash metadata), you may need to manually reflash the TinyUF2 bootloader using a SWD debug tool such as J-Link or OpenOCD.
> Refer to your board's documentation for additional recovery options if needed.

## Port Directory Structure

```
├── app.cmake
├── board_flash.c
├── boards
│   ├── apard32690
│   ├── max32650evkit
│   ├── max32650fthr
│   ├── max32666evkit
│   ├── max32666fthr
│   ├── max32690evkit
│   └── max78002evkit
├── boards.c
├── boards.h
├── CMakeLists.txt
├── family.cmake
├── linker
│   ├── max32650
│   ├── max32665
│   ├── max32690
│   └── max78002
├── README.md
└── tusb_config.h
```
