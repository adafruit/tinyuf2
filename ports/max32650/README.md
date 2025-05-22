# TinyUF2 - MAX32650 Port

This folder contains the port of TinyUF2 for Analog Devices' MAX32650 MCU.

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
- [Notes on SAVELOG=1](#notes-on-savelog1)
- [Cleaning Logs](#cleaning-logs)
- [Flashing Example Applications](#flashing-example-applications)
  - [Flashing via Drag-and-Drop](#flashing-via-drag-and-drop)
  - [Re-Entering Bootloader Mode](#re-entering-bootloader-mode)
- [Port Directory Structure](#port-directory-structure)


<br>

## Requirements

This guide focuses on building TinyUF2 for Analog Devices' MAX32 parts.
It is written with Windows users in mind using the **MSDK**, but TinyUF2 is fully portable and can be built with a standard toolchain on Linux and macOS.


### Requirements for Linux/macOS (Generic)

You do **not** need the MSDK to build TinyUF2 on Linux or macOS.
All you need is a basic toolchain:

- **GNU ARM Toolchain** (`arm-none-eabi-gcc`) available in your `PATH`
- **make**
- **git** (required for submodules)
- **SDK Dependencies**


### Installing SDK Dependencies
```bash
python tools/get_deps.py max32
```
or
```bash
python tools/get_deps.py --board max32650evkit
```

#### macOS Dependency Install
```bash
brew install arm-none-eabi-gcc make git
```

#### Ubuntu Dependency Install
```bash
sudo apt update
sudo apt install gcc-arm-none-eabi make git
```

<br><br>

```bash
# Example usage:
cd ports/max32650evkit/
make BOARD=max32650evkit all
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


<br>

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

Or in one-line command for building:

```bash
PATH="/c/MaximSDK/Tools/GNUTools/10.3/bin/:$PATH" make BOARD=max32650evkit blinky erase-firmware self-update
```

(Adjust the path if your MSDK installation is in a different location.)

<br>

## Available Boards

Each port supports multiple hardware platforms.
The specific boards available for each device can be found inside:

```
ports/maxxxxxx/boards/
```

For example, for MAX32650:

```
tinyuf2/ports/max32650/boards/
    max32650evkit
    max32650fthr
```

When building or flashing, make sure to specify a valid `BOARD` name from the available list:

```bash
make BOARD=max32650evkit all
make BOARD=max32650evkit flash
```

Otherwise, the build will fail if an invalid board name is provided.

<br>

## Building the Bootloader

1. Open your MSYS2 terminal (preferably MSDK’s).
2. Navigate to the port folder for MAX32650:

```bash
cd ports/max32650
```

3. Build the TinyUF2 bootloader:

```bash
make BOARD=max32650evkit all
```


Output files will appear in `_build/` and build logs under `apps/$(APP)/logs/`.


<br>

## Building Demo Applications

TinyUF2 for MAX32650 includes three demo applications:
- **Blinky** (`apps/blinky`)
- **Erase Firmware** (`apps/erase_firmware`)
- **Self-Update** (`apps/self_update`)

### To Build Individual Applications:

```bash
make BOARD=max32650evkit blinky
make BOARD=max32650evkit erase-firmware
make BOARD=max32650evkit self-update
```

### To Clean Individual Applications:

```bash
make BOARD=max32650evkit blinky-clean
make BOARD=max32650evkit erase-firmware-clean
make BOARD=max32650evkit self-update-clean
```

You can add `SAVELOG=1` to any of these commands to generate a saved build log.

```bash
 make BOARD=max32650evkit SAVELOG=1 blinky erase-firmware self-update
```

<br>

## Flashing the Bootloader


### J-Link vs OpenOCD

TinyUF2 supports two main ways to flash firmware:

- **J-Link** (default): Uses SEGGER's proprietary debug probe. Supports fast, reliable flashing and debugging over SWD or JTAG. Requires a J-Link device and SEGGER drivers.

- **OpenOCD (MSDK)**: Open-source tool for programming/debugging via CMSIS-DAP or other adapters.
  The MSDK includes a custom version of OpenOCD that supports MAX32 devices, since official OpenOCD does not yet have MAX32 flash algorithm support.


<br>

`make flash` will use **J-Link** by default.
`make flash-msdk` to use the **OpenOCD** path with CMSIS-DAP.



### 1. J-Link (default)

To flash using a J-Link debugger:

```bash
make BOARD=max32650evkit flash
```

To erase before flashing:

```bash
make BOARD=max32650evkit erase flash
```

### 2. OpenOCD from MSDK (optional)

If you prefer OpenOCD and you have it installed through MSDK:

```bash
make BOARD=max32650evkit flash-msdk
```

Make sure `MAXIM_PATH` is correctly set to the MSDK base folder. If your default installation of the MSDK is not `C:/MaximSDK` you can pass the MaximSDK directory's location...

```bash
make BOARD=max32650evkit MAXIM_PATH=C:/MaximSDK flash-msdk
```

> ⚠️ **Note:**
> Optional flash option when running within an installed MSDK to use OpenOCD. Mainline OpenOCD does not yet have the MAX32's flash algorithm integrated. If the MSDK is installed, flash-msdk can be run to utilize the the modified openocd with the algorithms.

<br>

## Notes on SAVELOG=1

Log export options are available for demo apps.

If `SAVELOG=1` is set during a build:

- Output logs are automatically saved into a `logs/` folder inside each application.
- Each application target (e.g., `blinky`, `blinky-clean`) has its own separate subfolder and timestamped `.log` files.
- Log files are ignored from Git version control.

Example:

```
apps/blinky/logs/blinky/blinky_20250425_134500.log
apps/blinky/logs/blinky-clean/blinky-clean_20250425_134512.log
```

<br>

## Cleaning Logs

You can remove all saved build logs across all apps by running:

```bash
make BOARD=max32650evkit clean-logs
```

This deletes all `logs/` directories under `apps/blinky`, `apps/erase_firmware`, and `apps/self_update`.


<br>


## Flashing Example Applications

After building any of the demo applications (Blinky, Erase Firmware, or Self-Update), a UF2 file will be generated in:

```
apps/<application>/_build/<board>/<application>-<board>.uf2
```

For example:

```
apps/blinky/_build/<board>/blinky-<board>.uf2
```

### Flashing via Drag-and-Drop

1. **Enter bootloader mode** on your board:
   - Typically, perform a **double-tap on the reset button** within **500 milliseconds**.
   - The board will appear as a **USB mass storage device** (for example, named `TINYUF2`) in your operating system's **File Explorer** (Windows) or **Finder** (macOS) or **File Manager** (Linux).

2. **Using your file explorer**, locate the `.uf2` file you built, and **drag and drop** it onto the mounted TinyUF2 USB drive.

3. The board will automatically reboot and begin running the new application.

### Re-Entering Bootloader Mode

To flash a different application or return to bootloader mode:

- Perform another **double-tap** of the reset button within 500 milliseconds.
- The board will reappear as a USB mass storage device for new UF2 flashing.

<br>

> ⚠️ **Note:**
> If double-tap reset does not work (for example, if the running application has corrupted necessary flash metadata), you may need to manually reflash the TinyUF2 bootloader using a SWD debug tool such as J-Link or OpenOCD.
> Refer to your board's documentation for additional recovery options if needed.

<br>

## Port Directory Structure

Example directory tree for the MAX32650 port:

```
max32650
├── Makefile
├── README.md
├── _build
├── apps
│   ├── blinky
│   │   ├── Makefile
│   │   └── _build
│   ├── erase_firmware
│   │   ├── Makefile
│   │   └── _build
│   └── self_update
│       ├── Makefile
│       └── _build
├── board_flash.c
├── boards
│   ├── max32650evkit
│   │   ├── board.h
│   │   └── board.mk
│   └── max32650fthr
│       ├── board.h
│       └── board.mk
├── boards.c
├── boards.h
├── linker
│   ├── max32650_app.ld
│   ├── max32650_boot.ld
│   └── max32650_common.ld
├── port.mk
└── tusb_config.h
```
