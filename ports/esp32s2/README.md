# UF2 Bootloader **Application** for ESP32-S2

The project is composed of customizing the 2nd stage bootloader from IDF and UF2 factory application as 3rd stage bootloader. **Note**: since IDF is actively developed and change very often, it is included as submodule at `lib/esp-idf`, please run export script there to have your environment setup correctly.

Following boards are supported:

- [Adafruit Magtag 2.9" E-Ink WiFi Display](https://www.adafruit.com/product/4800)
- [Adafruit Metro ESP32-S2](https://www.adafruit.com/product/4775)
- [Espressif Kaluga 1](https://docs.espressif.com/projects/esp-idf/en/latest/esp32s2/hw-reference/esp32s2/user-guide-esp32-s2-kaluga-1-kit.html)
- [Espressif Saola 1R (WROVER) and 1M (WROOM)](https://docs.espressif.com/projects/esp-idf/en/latest/esp32s2/hw-reference/esp32s2/user-guide-saola-1-v1.2.html)
- [Gravitech Cucumber RIS ESP32-S2 w/Sensors ](https://www.gravitech.us/curisdebowis.html)
- [LILYGO® TTGO T8 ESP32-S2 V1.1 ST7789 ](http://www.lilygo.cn/prod_view.aspx?TypeId=50033&Id=1321&FId=t3:50033:3)
- [microDev microS2](https://circuitpython.org/board/microdev_micro_s2)
- [Olimex ESP32S2 DevKit Lipo vB1 (WROVER and WROOM)](https://www.olimex.com/Products/IoT/ESP32-S2/ESP32-S2-DevKit-Lipo/open-source-hardware)
- [Unexpected Maker FeatherS2](https://feathers2.io)

## Build & Flash

### Build

You will need to first run `lib/esp-idf/export.sh (or bat)` to set up environment, then

```
make BOARD=adafruit_feather_esp32s2 all
```

### Flash

You could flash it with flash target

```
make BOARD=adafruit_feather_esp32s2 flash
```

or you could also use pre-built binaries from [release page](https://github.com/adafruit/tinyuf2/releases). Extract and run following esptool commands

```
esptool.py --chip esp32s2 -p /dev/ttyUSB0  -b 460800 --before=default_reset --after=hard_reset write_flash --flash_mode dio --flash_freq 80m --flash_size 4MB 0x8000 partition-table.bin 0xe000 ota_data_initial.bin 0x1000 bootloader.bin 0x2d0000 tinyuf2.bin
```

Note: you may need to change the `flash_size` and offset of `tinyuf2.bin` if your board is not 4MB.

## Usage

There are a few ways to enter UF2 mode:

- There is no `ota application` and/or `ota_data` partition is corrupted
- `PIN_BUTTON_UF2` is gnd when 2nd stage bootloader indicator is on e.g **RGB led = Purple**. Note: since most ESP32S2 board implement `GPIO0` as button for 1st stage ROM bootloader, it can be used for dual-purpose button here as well. The difference is the pressing order:
  - Holding `GPIO0` then reset -> ROM bootloader
  - Press reset, see indicator on (purple RGB) then press `GPIO0` -> UF2 bootloader
- `PIN_DOUBLE_RESET_RC` GPIO is attached to an 100K resistor and 1uF Capacitor to serve as 1-bit memory, which hold the pin value long enough for double reset detection. Simply press double reset to enter UF2
- Request by application using [system reset reason](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/system/system.html?highlight=esp_reset_reason#reset-reason) with hint of `0x11F2`. Reset reason hint is different than hardware reset source, it is written to RTC's store6 register and hold value through a software reset. Since Espressif only uses an dozen of value in `esp_reset_reason_t`, it is safe to hijack and use *0x11F2* as reset reason to enter UF2 using following snippet.
  ```
  #include "esp_private/system_internal.h"
  void reboot_to_uf2(void)
  {
    // Check out esp_reset_reason_t for other Espressif pre-defined values
    enum { APP_REQUEST_UF2_RESET_HINT = 0x11F2 };

    // call esp_reset_reason() is required for idf.py to properly links esp_reset_reason_set_hint()
    (void) esp_reset_reason();
    esp_reset_reason_set_hint(APP_REQUEST_UF2_RESET_HINT);
    esp_restart();
  }
  ```

## Convert Binary to UF2

To create your own UF2 file, simply use the [Python conversion script](https://github.com/Microsoft/uf2/blob/master/utils/uf2conv.py) on a .bin file, specifying the family as **0xbfdd4eee**. Note you must specify application address of 0x00 with the -b switch, the bootloader will use it as offset to write to ota partition.

To create a UF2 image from a .bin file:

```
uf2conv.py firmware.bin -c -b 0x00 -f 0xbfdd4eee
```

## 2nd Stage Bootloader

After 1st stage ROM bootloader runs, which mostly checks GPIO0 to determine whether it should go into ROM DFU, 2nd stage bootloader is loaded. It is responsible for determining and loading either UF2 or user application (OTA0, OTA1). This is the place where we added detection code for entering UF2 mode mentioned by above methods.

Unfortunately ESP32S2 doesn't have a dedicated reset pin, but rather using [power pin (CHIP_PU) as way to reset](https://github.com/espressif/esp-idf/issues/494#issuecomment-291921540). This makes it impossible to use any RAM (internal and PSRAM) to store the temporary double reset magic. However, using an resistor and capacitor attached to a GPIO, we can implement a 1-bit memory to hold pin value long enough for double reset detection.

**TODO** guide and schematic as well as note for resistor + capacitor.

## UF2 Application as 3rd stage Bootloader

UF2 is actually a **factory application** which is pre-flashed on the board along with 2nd bootloader and partition table. When there is no user application or 2nd bootloader "double reset alternative" decide to load uf2. Therefore it is technically 3rd stage bootloader.

It will show up as mass storage device and accept uf2 file to write to user application partition. UF2 bootloader will always write/update firmware to **ota_0** partition, since the actual address is dictated by **partitions.csv**, uf2 file base address **MUST** be 0x00, the uf2 will parse the partition table and start writing from address of ota_0. It also makes sure there is no out of partition writing.

After complete writing, uf2 will set the ota0 as bootable and reset, and the application should be running in the next boot.

NOTE: uf2 bootloader, customized 2nd bootloader and partition table can be overwritten by ROM DFU and/or UART uploading. Especially the `idf.py flash` which will upload everything from the user application project. It is advisable to upload only user application only with `idf.py app-flash` and leave other intact provided the user partition table matched this uf2 partition.

## Partition

The following partition isn't final yet, current build without optimization and lots of debug is around 100 KB. Since IDF requires application type must be 64KB aligned, uf2 is best with size of 64KB, we will try to see if we could fit  https://github.com/microsoft/uf2/blob/master/hf2.md and https://github.com/microsoft/uf2/blob/master/cf2.md within 64KB.

UF2 only uses `ota_0` user application can change partition table (e.g increase ota_0 size, re-arrange layout/address) but should not overwrite the uf2 part. If an complete re-design partition is required, `uf2_bootloader.bin` and the `modified 2nd_stage_bootloader.bin` should be included as part of user combined binary for flash command.

```
# Name,   Type, SubType, Offset,  Size, Flags
# bootloader.bin,,          0x1000, 32K
# partition table,          0x8000, 4K

nvs,      data, nvs,      0x9000,  20K,
otadata,  data, ota,      0xe000,  8K,
ota_0,    0,    ota_0,   0x10000,  1408K,
ota_1,    0,    ota_1,  0x170000,  1408K,
uf2,      app,  factory,0x2d0000,  256K,
ffat,     data, fat,    0x310000,  960K,
```
