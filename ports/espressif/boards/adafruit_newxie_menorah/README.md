# Adafruit Newxie Menorah

Rev A uses an ESP32-S3-MINI-1-N4R2 with 4 MB flash and 2 MB quad PSRAM.
TinyUF2 runs from internal RAM. The USB drive is `NEWXIEBOOT`, with
VID:PID `239A:0181`.

The optional Newxie in socket **J1** displays the standard TinyUF2 screen in
landscape orientation. It is a write-only 135 x 240 ST7789 panel on
MOSI33/SCK34, CS41, DC15, and backlight46, without a reset signal.
The other sockets have CS pull-ups and backlight pull-downs and are not
driven by this bootloader. No TFT is required for USB firmware updates;
the NeoPixel on GPIO42 provides status with or without a display.

To enter TinyUF2, tap RESET and then press BOOT during the purple NeoPixel
window. Holding BOOT while resetting enters the ROM downloader instead.
There is no double-reset RC circuit on this board. Applications can also
request TinyUF2 using the `0x11F2` reset hint documented in the port README.

Build from `ports/espressif` using the ESP-IDF version supported by this port:

```sh
idf.py -B build-newxie -DBOARD=adafruit_newxie_menorah build
```

The flash layout is `partitions-4MB-noota.csv`: the application starts at
`0x10000`, TinyUF2 at `0x2d0000`, and FAT storage at `0x310000`. Applications
must use this partition layout. Convert the application binary to UF2 with
family `ESP32S3` and base address `0`, then copy it to `NEWXIEBOOT`.

Bench-tested on Rev A on 2026-11-10: USB mass storage and CDC enumerate as
`239A:0181`, the J1 display shows the TinyUF2 screen, and USB firmware updates
work with J1 unplugged. Copying the Arduino bring-up UF2 starts the application,
which reports working PSRAM, MPR121 initialization, and Wi-Fi scanning.
