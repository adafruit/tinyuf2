# Adafruit Metro ESP32-P4

This port uses the Metro's 16 MB external flash and USB-C connector. TinyUSB's
full-speed OTG controller is routed to GPIO24/25, normally used by Serial/JTAG.
The USB-A high-speed port is not used. The bootloader drive is `METROP4BOOT`
(VID:PID `239A:017B`). Logs use UART0 so USB logging cannot stall the bootloader.

## Double reset hardware

Replace **CBATRAW with 2.2 µF**. Keep the existing 1 MΩ / 1 MΩ battery divider
on **GPIO18 / ADC1 channel 2**. The original 0.1 µF capacitor is too small for
the intended reset timing. This firmware does not change the PCB files.

On an external reset, the second-stage bootloader reads the node using eFuse
ADC calibration. A voltage above 2.5 V is a reset marker, distinct from the
normal battery reading of at most 2.1 V. Otherwise it drives the node HIGH
during the existing 500 ms detection window. A second reset in that window
leaves charge for the next boot to detect. Afterward it discharges the marker
for 5 ms and releases the pin with both pulls disabled.

The divider's nominal time constant is 1.1 seconds. From 3.3 V, the capacitor
stays above 2.5 V for approximately 0.31 seconds with VBAT at 0 V, or 0.65–1.21
seconds with VBAT at 3.0–4.2 V. These are estimates: capacitor tolerance,
effective capacitance, leakage, reset-button hold time, and boot latency need
bench verification. Applications should allow about **5.5 seconds** after
marker discharge before relying on a battery reading (about 1% settling).

If calibration is unavailable or a conversion times out, the bootloader skips
ADC detection and still supports the BOOT button. The ADC helper preserves
the bootloader's ADC entropy configuration and does not use the application
ADC driver.

## Entry and recovery

- Double-tap RESET with the modified capacitor fitted.
- Or tap RESET, then press BOOT while the NeoPixel is purple.
- Hold BOOT while resetting to enter the ROM downloader, independently of
  TinyUF2. BOOT is GPIO35 on this board.
- A 1200-baud touch on TinyUF2's CDC interface requests the ROM downloader.
- An application can request TinyUF2 with the existing `0x11F2` reset hint.

### Bench verification — 2026-10-10

Tested with ESP-IDF v5.4.3 on a rev v0.1 P4 with USB power, no LiPo, and a
hand-reworked CBATRAW capacitor. The installed capacitance was not independently
confirmed.

- An Arduino preflight measured 2.138 V at idle, 3.283 V with the weak pull-up,
  and 0.073 V with the weak pull-down. After a 500 ms HIGH drive, the node
  remained above 2.5 V for approximately 1.43 seconds.
- TinyUF2 enumerated as `METROP4BOOT` with CDC on Windows.
- Copying the generated blinky UF2 started the application and restored the
  Serial/JTAG interface. All 621 UF2 payload blocks subsequently matched
  readback through `CURRENT.UF2`.
- A single physical reset left the board in application mode. A quick physical
  double-reset returned to `METROP4BOOT`; the user confirmed the green ready
  indicator.
- A 1200-baud CDC touch entered the ROM downloader. Esptool connected without
  issuing a reset, read the MAC, and requested a normal reset afterward.

The initial bit-banged reset indicator appeared excessively bright. Replacing
the P4 bootloader transmitter with hardware RMT pulses fixed it: the user
confirmed a dim purple reset window followed by normal orange application
blinking. A subsequent double-reset on the updated build again enumerated
`METROP4BOOT`. Brightness settings were unchanged. The transmitter uses the same
WS2812 timings as the working application and TinyUF2 indicators, with a bounded
timeout and LOW output on completion or failure. It currently supports one
NeoPixel. Other ESP32 targets keep their existing transmitter.

The full P4 build and a Metro S3 bootloader compile passed. The P4 second-stage
bootloader uses 24,208 bytes of its 24,576-byte allocation. Battery operation
(including VBAT at 3.0 V), cold-start behavior, and detection timing limits remain
unverified. The full original flash image was backed up privately before
installation.

The subsequent ESP-IDF v6.1 build passes for TinyUF2, blinky, and self-update.
Its second-stage bootloader is 23,872 / 24,576 bytes with error-only boot logs;
TinyUF2 is 254,224 / 262,144 bytes. A Metro S3 bootloader regression compile
passes with the installed v5.4.3 toolchain.

The v6.1 hardware retest also passed: MSC/CDC enumeration after flashing, UF2
upload and application startup with Serial/JTAG restored, a dim purple
single-reset window followed by orange blinking, physical double-reset entry,
and 1200-baud ROM recovery verified by an esptool connection without reset.
All 814 blocks of the corrected blinky UF2 matched `CURRENT.UF2` readback.
The demo and self-update applications inherit the board defaults so their
image headers also target rev 0.1; IDF 6.1's default rev 3.1 images cannot run
on this board. Both rebuilt application headers were checked.

## Build and install

Use ESP-IDF **v6.1**. The board configuration selects the original P4 silicon
(minimum rev 0.1), not IDF 6.1's default ECO3 target. From `ports/espressif`:

```sh
idf.py -B build-metro-p4 -DBOARD=adafruit_metro_esp32p4 build
idf.py -B build-metro-p4 -DBOARD=adafruit_metro_esp32p4 -p PORT flash
```

The partition layout is `partitions-16MB-ota4MB.csv`: two 4 MB application
slots, TinyUF2 at `0x810000`, and FAT storage at `0x850000`. Initial installation
writes the bootloader and partition table; preserve any existing firmware and
data first. The P4 second-stage bootloader starts at `0x2000`, unlike S2/S3.
Use the generated flash arguments, not another board's offsets.

Convert an application binary (not a merged flash image) using family
`ESP32P4` / `0x3d308e94` and base address `0`. Applications must use the same
partition layout. The build also produces the standard blinky and TinyUF2
self-update applications.
