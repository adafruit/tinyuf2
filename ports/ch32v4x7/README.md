# Metro CH32V407 / CH32V467

This port supports the Rev A Metro boards with CH32V407RET6 or CH32V467RET6,
512 KB code flash, 200 KB SRAM, a 25 MHz crystal, USBHS1 on PA11/PA12 and
the D13 LED on PB12. External PSRAM is not used by the bootloader.

| Board | Build name | USB VID:PID | Drive |
| --- | --- | --- | --- |
| Metro CH32V407 | `metro_ch32v407` | `239A:017D` | `METRO407` |
| Metro CH32V467 | `metro_ch32v467` | `239A:017F` | `METRO467` |

USB IDs are allocated in Adafruit's `MBAdafruitBoards/Production/usb_vid_pid.csv`.
The shared UF2 family ID, **`0x7b8c32a7` (`CH32V4X7`)**, is registered in
[Microsoft's UF2 registry](https://github.com/microsoft/uf2/pull/109).

## Build and initial installation

From the repository root, with CMake, Ninja and `riscv-none-elf-gcc` on PATH:

```sh
git submodule update --init lib/tinyusb lib/uf2
python tools/get_deps.py ch32v4x7
cmake -S ports/ch32v4x7 -B cmake-build/metro407 -G Ninja \
  -DBOARD=metro_ch32v407 -DCMAKE_BUILD_TYPE=MinSizeRel -DLOG=0
cmake --build cmake-build/metro407
```

Substitute `metro_ch32v467` for the other board. Program `tinyuf2.elf` with
a compatible WCH SWIO probe, using sector erase and readback verification.
The bootloader occupies `0x00000000` through `0x00007fff`; its physical flash
alias is `0x08000000`. Preserve any existing application before installation.
No option bytes or hardware write-protection settings are changed.

The Hydra OEP probe used during development connects GPIO2 to PA13/SWIO,
GPIO6 to NRST, and GND to GND. Power the Metro from its own USB connector.
This uses WCH's single-wire debug transport.

## Using UF2

Double-tap RESET within 500 ms to enter the bootloader. With no valid app,
the drive appears automatically. Copy a matching application UF2 to the drive;
the board restarts into the app when the complete file has been programmed.
Subsequent application uploads need only USB and RESET.

Applications must be linked at **`0x8000`**, with **480 KB** available flash.
UF2 target addresses must use the zero-based address, not the physical alias.
The port accepts 256-byte, aligned UF2 payloads. Convert an application binary:

```sh
python lib/uf2/utils/uf2conv.py -c -b 0x8000 -f 0x7b8c32a7 \
  -o application.uf2 application.bin
```

An ordinary image linked at zero cannot be relocated by changing the UF2
conversion address. Its reset code and vector table must be linked at `0x8000`.
For ArduinoCore-CH32RV 0.6.0, the app linker script also needs its vector-table
assertion changed from `_vector_base == 0` to `_vector_base == ORIGIN(FLASH)`.
Disable that core's factory-ROM 1200-baud touch when using this bootloader;
double-reset is the supported entry method here.

Flash writes outside the application region are rejected. The application's
first sector is erased when an update starts and held in RAM until all UF2
blocks arrive. Its vector block is programmed last. An interrupted file copy
therefore returns to the bootloader after reset; copy the complete file again.
This is recovery from an interrupted upload, not a dual-image rollback scheme
or a guarantee against power loss during the final flash-program operation.

Erases are checked by readback, including the first sector before any later
sectors are modified. The first sector's data is verified before its vector
block is installed; a failed vector-block readback invalidates that sector.
Write and final-flush failures are reported to the host as USB mass-storage
write errors. The bootloader stays responsive and rejects further application
writes in that failed session. Reset the board before retrying a complete UF2.
Existing option-byte protection is preserved; protected flash must be unlocked
separately before retrying.

`CURRENT.UF2` contains the 480 KB application region. Bootloader self-update
over UF2 is not implemented; changing the bootloader still needs the probe.

## Implementation sources

- WCH's common V4x7 SDK, mirrored by [CH32 RISC-V User Group](https://github.com/ch32-riscv-ug/CH32V407),
  pinned by `tools/get_deps.py`. Its flash implementation is shared by V407 and V467.
  Vendor code retains WCH's restriction to WCH microcontrollers.
- The USB driver adapts Ha Thach's MIT-licensed
  [CH32H417 USBHS driver](https://github.com/hathach/tinyusb/pull/3779), commit
  `0c97a1c7b9b61dc66b890525f700fd45343650e6`, to V4x7's USBHS1 registers and IRQ.
  It is local to this port; TinyUSB's pinned submodule is unchanged.
- Application entry uses a software interrupt, following WCH's V4x7 IAP
  example, so application reset code executes with machine-mode CSR access.

The Metro bench checks cover enumeration, UF2 upload, application readback,
USB serial echo from the uploaded application, double-reset, shuffled/duplicate
blocks and interrupted-copy recovery. They do not constitute USB compliance
testing or the repository's separate HIL rig battery.
