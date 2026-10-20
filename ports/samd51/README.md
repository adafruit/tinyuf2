# TinyUF2 for SAMD51

Port for SAMD51 with the 1 MB / 256 KB parts (SAMD51N20A). Boards:

| Board | Notes |
| --- | --- |
| `intech_grid` | Intech Studio Grid modules, volume `GRID26` |
| `intech_wrid` | Same hardware and USB IDs as `intech_grid`, volume `WRID26`, to tell the two bootloaders apart |

## Flash layout

| Address | Content |
| --- | --- |
| `0x00000000` | TinyUF2, 16 KB, write protected with BOOTPROT |
| `0x00004000` | Application |

The application must be linked at `0x4000`. To create a UF2 image from a `.bin` file:

```
uf2conv.py -c -b 0x4000 -f 0x55114460 firmware.bin
```

## Entering the bootloader

- Hold the button (`PC11`, active low) while the board resets or is plugged in.
- The bootloader also stays when the application is missing or invalid.
- Double tap and reboot from application are not implemented.

## Self-update

`update-tinyuf2.uf2` is built next to the bootloader in `_bin/<board>/apps`. Copy it to the bootloader drive: it runs from the application area,
rewrites the bootloader and invalidates itself, then the new bootloader starts. The application area is overwritten, so
copy the application again afterwards.

- The bootloader protects itself on every boot: if the BOOTPROT fuse in the user page does not match the 16 KB boot size, it is rewritten
  and the board resets once. The self-update lifts the protection until the next reset (`SBPDIS`) to write the new bootloader.
- Rewriting the BOOTPROT fuse erases the user page before it is programmed again. A power cut in between leaves the user page blank,
  and the bootloader then leaves it alone: restore it with an SWD probe.
- Updating between `intech_grid` and `intech_wrid` works the same way, the drive label shows which one is installed.
- A power cut while the bootloader area is erased leaves the board without a bootloader: recover it with an SWD probe. To program the
  bootloader over SWD, first remove the protection with `atsame5 bootloader 0` in OpenOCD and reset.

## Debugging

- `BOD33` is set to 2.7 V at start. The default level is too low and flash writes can store zeros.
- The application usually takes over the SWD pins. Hold the button while powering up so the bootloader runs and SWD stays usable.
- The bootloader must fit in 16 KB. A Debug build or logging (`-DLOG=1 -DLOGGER=RTT`) does not: the Debug build type increases the boot
  size to 64 KB, and the application then has to be linked at `0x10000`.
- Flash with openocd and a CMSIS-DAP probe: `cmake --build build --target tinyuf2-openocd`. It lifts the bootloader protection first,
  the bootloader protects itself again at boot.
