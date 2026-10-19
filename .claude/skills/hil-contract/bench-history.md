# HIL bench history

Part of the HIL contract (`SKILL.md` beside this file): the measurements and dated bench observations behind its Limits.

## RT boards

metro_m7_1011 and imxrt1060_evk.

`install` from a blank board, or one whose ROM found no boot image, brings up DFU (measured on imxrt1060_evk 2026-10-12 and metro_m7_1011 2026-10-13). With no boot image a new J-Link session reads the flash wrong (imxrt1060_evk: zeros; metro_m7_1011: bytes shifted) until a `loadbin` has run; a `loadbin` compare reads it right. On metro_m7_1011, J-Link then prints "Invalid flash header detected." at the install's first reset.

On metro_m7_1011 (2026-10-13, J-Link V9.84), `tinyuf2-jlink`'s `loadfile` of the cmake HEX (0x60000400 on) reported "1 range affected (65536 bytes)" and, from a fresh session after it, 0x60000000, 0x6000BF00, 0x6000C000-0x6000C00F, 0x6000C200 and 0x6000FF00 read 0xFF while 0x60010000 kept its data. Its compare covered the whole block: over blinky it programmed, and right after a program it skipped ("Contents already match"). DFU came up within 2 s in each of these three runs. That every install by the target leaves [0x6000C000, 0x60010000), the app's first 16 KiB, erased is an inference from these samples and this HEX, not a measurement of every case.

On imxrt1060_evk (2026-10-13), the same target over blinky also reported "1 range affected (65536 bytes)"; from a fresh session after it, blinky's vectors at 0x6000C000-0x6000C00F and 0x6000C200 read 0xFF, while the FCB at 0x60000000 and 0x60010000 kept their data.

## imxrt1064_evk

On imxrt1064_evk (2026-10-18, the ci.lan rig, J-Link V9.78 on an external J-Link, S/N 000725299165, with "an old firmware
module: V1"; DIGPROG 0x006C0000, the marking that decides the silicon revision not read, the rig being remote, so both
IMXRT1064CE_A Rev 1.3 and IMXRT1064CE_B Rev 1.1 were checked), `tinyuf2-jlink`'s `loadfile` of the cmake HEX
([0x70000000, 0x70007134)) reported "1 range affected (65536 bytes)": from a fresh session after it, sentinels at 0x7000BF00
and 0x7000C000 (the app start) read 0xFF while 0x70010000 kept its data. So every install leaves [0x7000C000, 0x70010000),
the app's first 16 KiB, erased, as on the RT1060 (an inference from this sample and this HEX). The sentinels had been
programmed by `loadbin` over [0x7000BF00, 0x70010004) ("1 range affected (131072 bytes)"), which erased the FCB with block
0: a fresh session then read every flash word, the sentinels included, as 0xFF (no boot image, as on the RT1060), while
a session whose `loadbin` compare had run ("Contents already match") read them right. The install's reset after the
download printed "Could not find valid reset vector." then "Target halted on flash header read." (`BENIGN`, the RT1062
note), and "Invalid flash header detected." at the implicit reset before the download while the FCB was erased. DFU came
up with serial BAE96FB95AFA6DBB8F00005002001200 (volume RT1064BOOT) at 1-1.2, on the same hub (1-1) as the probe at
1-1.1: the farm's cabling, which this contract's Limits records. The word at 0x20000FFC (the fixture's stack top, less
4, in DTCM) took a written value and read it back, then its saved value 0, so DTCM is enabled at the ROM default; the
FlexRAM fuse itself was not read.

## stm32f303disco

On stm32f303disco (2026-10-14, J-Link V9.84 on the board's J-Link OB), `tinyuf2-jlink`'s `loadfile` compared [0x08000000, 0x08004000) and reprogrammed only the 2 KiB pages that differed, erasing the rest of such a page past the image (a sentinel at 0x08003F00 read 0xFF from a fresh session after it), while 0x08004000 (the app start) and 0x08004800 kept their data. So an install keeps a valid app. DFU still came up without the fallback in the battery of 2026-10-14: the runner's verify session halted the core in TinyUF2's double-tap wait (`src/main.c`, magic armed), so its reset entered DFU as a double tap, an inference from that trace. When that reset misses the window the app boots, and the retained-register fallback brings DFU up after `dfu`'s 20 s wait.

stm32f303disco does not signal a disconnect when TinyUF2 comes up after a reset (by design, MB1035 Rev D.1 sheet 4, book 6582, the bench board's revision not read: USB USER's D+ has a fixed 1.5 kΩ pull-up, R16, to the 3V rail the ST-LINK USB keeps powered, so D+ stays high through an MCU reset; the F303 has no internal D+ pull-up, DS9118 Rev 14 Table 66 note 2; on the bench the host kept the old device), so the host does not re-enumerate it unless it was polling the device (TinyUF2 as an MSC disk) when the reset came. Its roster `usbPower` names its USB USER port on the Port Authority hub (PA40004, port 3).

A bench `uhubctl` cycle, a raw hub request, that met an enumeration in progress on hub 1-1 of an AMD 500-series xHCI controller killed that controller (2026-10-14: "HC died", every device on its buses lost, recovered by unbinding and binding `xhci_hcd`; the Port Authority hub needed a replug); hence the kernel's serialized `disable` and the 2 s in state `default`. On this hub `disable` 1 reads `off` from `uhubctl` (2026-10-14).

## stm32f303vc

On stm32f303vc, TinyUF2 write-protects its pages 0-7 at boot through the option bytes unless RCC_CSR's OBLRSTF is set, and it never clears that flag, so after any option-byte reload it skips protection until a power-on reset. A J-Link connect to a chip with that protection set prints the `BENIGN` unlock note and, read from a fresh `-device Cortex-M4` session after it, leaves the option bytes at RDP 0xAA with no WRP and flash intact (three samples, 2026-10-14). Its double-tap word is the last SRAM word, 0x20009FFC; that it survives SYSRESETREQ is undocumented (RM0316 Rev 10, DS9118, PM0214, ES0204) and inferred from the commissioning run (2026-10-14: the reset without the magic booted the app, the one with it entered DFU and consumed it).

## stm32f411ve_discovery

On stm32f411ve_discovery (2026-10-15, J-Link V9.84 on the board's J-Link OB, rev A silicon: DBGMCU REV_ID 0x1000, ES0287 Rev 6), `tinyuf2-jlink`'s `loadfile` of the HEX ([0x08000000, 0x08003E18)) reported "1 range affected (16384 bytes)": from a fresh session after it, a sentinel at 0x08003F00 read 0xFF while sentinels at 0x08004000, 0x08007C00, 0x08008000, 0x0800C000, 0x08010000 (the app start) and 0x08010800 kept their data. So an install keeps a valid app.

TinyUF2 write-protects sectors 0-1 at every boot (`src/main.c`; on the F4 the option bytes take effect when OPTSTRT completes, with no reset, RM0383 Rev 4 3.6.2). A `-device stm32f411ve` connect to a chip with that protection prints the unlock note (J-Link transcript shape) and removes it by resetting the chip: with RCC_CSR cleared and TinyUF2 booted, the next such connect read RCC_CSR 0x14000000 (SFTRSTF, PINRSTF) and nWRP 0xFF, while a `-device Cortex-M4` connect read RCC_CSR 0 and nWRP 0xFC, the core running the app. A runner session that reset the chip that way after a retained-register re-entry booted the app and dropped DFU; the unlock is not in UM08001 Rev 9.78. Right after the flash target's unlock, a `Cortex-M4` session's halt failed ("CPU could not be halted", flash read back wrong) with no delay (three runs) and succeeded after a 200, 400, 600, 800 or 1500 ms `sleep`; TinyUF2's boot rewriting the option bytes is the inferred cause, and no rewrite time is documented.

Its double-tap word is 0x2000FFFC, the last word of the boot script's 64 KiB RAM; that it survives SYSRESETREQ is undocumented (RM0383 Rev 4 6.1.1) and inferred from the commissioning run (the reset without the magic booted the app, the one with it entered DFU and consumed it). DFU re-enumerated after each tested reset into DFU without port power control (OTG FS soft disconnect).

## stm32h563_nucleo

On stm32h563_nucleo (2026-10-15, STM32CubeProgrammer v2.23.0 on the board's STLINK-V3, STM32H563ZI rev Z), `tinyuf2-stlink` erased exactly the 8 KiB sectors holding HEX data (sectors 0 and 1 for a 15 KiB image): from a fresh session after it, a sentinel at 0x08003F00 read 0xFF while 0x08004000 and 0x08008000 (the app start) kept theirs. So an install keeps a valid app.

TinyUF2 sets no write protection on the H5 today: WRPSGn1 stayed 0xFFFFFFFF after it booted, since its boot-time call reads the option bytes with no bank selected. The H5's D+ pull-up is internal (RM0481 Rev 5 USB_BCDR.DPPU_DPD, reset value 0), so a reset shows the host a disconnect; its hub, 5-2 on htpc, has ganged power. The double-tap word is SRAM3's last, 0x2009FFFC, which a system reset keeps with option SRAM1_3_RST=1 (RM0481 Table 43; set on this chip).

The H5's debug AP stops answering after a killed ETM trace session until a power cycle (agentrc `etm-trace` notes; seen again 2026-10-15 before commissioning). Another board's run on the same hub can reset this one: on 2026-10-15 a P4 battery's ROM-mode enumeration errors on 5-2.3 made the hub power-cycle that port and reset 5-2.7 mid-read, and `install`'s FAT read timed out (exit 4).

## J-Link

J-Link's QSPI loader is undocumented (SEGGER UM08001 has nothing on it). Historically, at sampled sentinel points on both RT boards, the runner's former `loadbin` install (no longer issued) lost the rest of its 64 KiB block past the image while a sentinel at 0x60010000, in the next block, survived; a sample, not a guarantee for every image.

`JLinkExe` sometimes crashes in `libjlinkarm` at the probe connect on htpc (SIGSEGV; once a glibc double-free abort); the cause is unknown. Seen in 2 of 94 runner sessions on 2026-10-12.

## Shared hubs

A device hung mid-write makes the host controller retry its enumeration, which stalled a J-Link connect on the same hub for ~80 s (lpcxpresso55s69); that the hub is the cause is a hypothesis.

Port cycle reach (enumeration-reach evidence only: physical power removal on 5-3 was not measured), measured 2026-10-17 on htpc (kernel 6.12) on hub 5-3 (Adafruit Port Authority PA40004, Microchip USB2514B, `uhubctl` reports `ppps`), under a hold of every board on it (metro_m7_1011, espressif_p4_function_ev, bench_esp32s3 and espressif_esp32s3_devkitc_1): writing `disable` 1 then 0 on an empty port (5-3.1) produced no kernel log line and no device-number change on 5-3.2 or 5-3.4; the same on the occupied port 5-3.4 (the P4's USB-Serial-JTAG unit) disconnected and re-enumerated only that device (device number 69 to 14) while 5-3.2 kept device number 73. Not measured: whether VBUS on the cycled port actually dropped (no meter or bus-powered indicator was used, and a hub with no power switch would show the same disconnect and re-enumeration), an enumeration storm (no safe way to manufacture one), and the ganged hubs 5-1 and 5-2 (Terminus FE 2.1, 1a40:0201, `uhubctl` reports `ganged`), whose other devices are not rig boards.

Documented (read-doc, 2026-10-17): USB Specification 2.0 (book 775), section 11.11, p363: with per-port power switching a port's power is off in the Powered-off state; with ganged switching "the power to a gang is not turned off unless all ports in a gang are in the Powered-off or Not Configured states", so a `usbPower` cycle of one port on a ganged hub removes no power while another port in the gang is powered, and can switch the whole gang off when it is the last. Section 11.11 also lets a hub with no power switches report per-port switching, and 11.11.1 requires a hub with several gangs to report it, so `ppps` alone does not prove a port's power is switched on its own. Microchip DS00001692 USB251xB data sheet (book 6533), p19 and p22: individual port power switching is the default strap (`PORT_PWR`), and the ability to switch per port is "hardware implementation dependent" (p22). Microchip DS80000627D USB251xB errata (book 6531), module 4, p4: a full-/low-speed device that self-detaches and re-attaches within 100 µs of SE0 may not be seen as a detach, and "may result in a failure to establish a connection after re-attach"; workaround 2 is a port reset. No Terminus FE 2.1 document is in the library (searches FE2.1, Terminus, 1a40: no match). The kernel's `disable` attribute (drivers/usb/core/port.c `disable_store`, v6.12.48) clears PORT_POWER through `usb_hub_set_port_power`, which sends ClearPortFeature(PORT_POWER) for that port only.

Board design (read-pcb, 2026-10-18): the Port Authority is inferred to be Adafruit's Smart HIL Hub (adafruit/MBAdafruitBoards `Development/HIL Bench/Smart HIL Hub`, @ a2003e8687c1), the only four-port USB2514B design in that repository; its strings and configuration live in its EEPROM (U14), which was not read, and its revision is not known. Revisions A, B and C wire it the same way: each `PRTPWRn` drives the EN pin of its own Diodes AP22653 load switch (U2, U6, U8, U10 for ports 1-4), and each switch's output feeds only its own port: USB-A VBUS, JST-XH header, 100 µF, and a green LED to ground through 2.2 kΩ, so no port's power is ganged. The PRTPWR nets carry no battery-charging strap, but the EEPROM can still enable battery charging (USB251xB data sheet, book 6533, p18-19). Documented (read-doc): the hub asserts PRTPWR to enable VBUS through the switch's EN (book 6533, p17, §4.1.1); the AP22653's enable is active-high, and a disabled switch discharges its output through 600 Ω typical "for limited time", a duration the data sheet does not give (Diodes DS41186 Rev 5-2, book 6580, p1, p5 Note 9, p11). If that discharge lasts, an unloaded port's 100 µF falls with τ ≈ 60 ms, below 1 % of 5 V in about 0.3 s, inside the runner's 1 s off (`PortPower.OFF`); if it stops early, the LED branch drains the port only to about the LED's forward voltage. This is a design estimate, not a measurement. It does not cover a self-powered board that back-drives VBUS. stm32f303disco, the one `usbPower` board (port 3), is powered from its ST-LINK USB, but by design its USB USER VBUS goes only to two series BAT60J Schottky diodes pointing into the board's 5V (D4, D5, MB1035 Rev D.1 sheet 4, book 6582), so it does not back-drive the port beyond their reverse leakage; the bench board's revision was not read, and a cycle of port 3 itself was never measured. The INA3221 (IC2) senses ports 1-3's switched VBUS and is reachable only through the hub's STEMMA QT I2C header, so an I2C adapter there could measure the drop on port 3; that has not been tried.

## espressif_p4_function_ev JTAG route

Commissioned 2026-10-20 on htpc (ESP32-P4 rev v1.0, openocd-esp32 v0.12.0-esp32-20260703, agentrc 4f6a028). Documented (read-doc): the USB Serial/JTAG controller is a full-speed CDC-ACM and JTAG device on an internal PHY (ESP32-P4 TRM Rev 0.7, book 6567, p3187-3188); `EFUSE_USB_PHY_SEL` 0 gives it the GPIO24/25 PHY and OTG11 the GPIO26/27 one (p942; the bench chip's value was not read). RTS=1 with DTR=0 on its CDC resets the SoC (Table 54.3-2, p3190), a "USB (UART) reset", classified as an HP Core Reset (Table 11.1-1, p1082-1083); the TRM does not say whether the controller's USB connection survives it, and Deep-sleep powers it down (p3195). The errata (book 6568 v1.4) list nothing for it. Measured: the USJ (5-3.4) kept its device number through esptool hard resets, polled every 2 ms for 3 s after three sessions, and stayed available through two battery runs over the route (`run --route openocd_esp`, 04:30 and 04:33), whose esptool sessions follow the install; then `install` and `restore` under a hold passed, as did three restores before them. Each provider session logged no failed event and only "Reset cause (24)".

The runner waits one second after its esptool session's hard reset before the provider starts. Without it (openocd started ~4 ms after the session ended), 6 of 6 route restores failed every `reset init` of the session: `reset-assert-post` could not write 0x500c2064 (sysbus access failed, target not halted) and the reset cause read 3, software system reset. The provider stopped before writing each time. Plain openocd sessions after the same esptool session passed 17 of 17 (driven by `-c` or over Tcl, the provider's argv and wrapper, 0.15-2 s gaps); the provider called ~150 ms after it passed 4 of 4 and called immediately failed 2 of 2. The cause is unknown (agentrc #160).

## esptool boards

At the end of a UF2 copy TinyUF2 restarts while the host's usb-storage is still talking to it: the host log shows a reset of that device and read errors on its block device. Seen on the S3 and the P4; other ports are unchecked. On the P4, while an esptool session holds the chip, the host log shows a full-speed device on TinyUF2's USB path that never answers its descriptor request (htpc 2026-10-14); the battery passed with it.
