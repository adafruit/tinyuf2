# UF2 Bootloader **Application** for ESP32S

The project is composed of customizing the 2nd stage bootloader from IDF and UF2 factory application as 3rd stage bootloader. Supported boards are:

- [Espressif Saola 1R (WROVER) and 1M (WROOM)](https://docs.espressif.com/projects/esp-idf/en/latest/esp32s2/hw-reference/esp32s2/user-guide-saola-1-v1.2.html)
- [Espressif Kaluga 1](https://docs.espressif.com/projects/esp-idf/en/latest/esp32s2/hw-reference/esp32s2/user-guide-esp32-s2-kaluga-1-kit.html)

## Usage

There are a few ways to enter UF2 mode:

- There is no `ota application` and/or `ota_data` partition is corrupted
- `PIN_BUTTON_UF2` is gnd when 2nd stage bootloader indicator is on e.g **RGB led = Purple**. Note: since most ESP32S2 board implement `GPIO0` as button for 1st stage ROM bootloader, it can be used for dual-purpose button here as well. The difference is the pressing order:
  - Holding `GPIO0` then reset -> ROM bootloader
  - Press reset, see indicator on (purple RGB) then press `GPIO0` -> UF2 bootloader
- `PIN_DOUBLE_RESET_RC` GPIO is attached to an 100K resistor and 1uF Capacitor to serve as 1-bit memory, which hold the pin value long enough for double reset detection. Simply press double reset to enter UF2
- Request by application using [system reset reason](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/system/system.html?highlight=esp_reset_reason#reset-reason) with hint of `0x11F2`. Reset reason hint is different than hardware reset source, it is written to RTC's store6 register and hold value through a software reset. Since Espressif only use an dozen of value in `esp_reset_reason_t`, it is safe to hijack and use *0x11F2* as reset reason to enter UF2 using following snippet.
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

## 2nd Stage Bootloader

After 1st stage ROM bootloader runs, which mostly checks GPIO0 to determine whether it should go into ROM DFU, 2nd stage bootloader is loaded. It is responsible for determining and loading either UF2 or user application (OTA0, OTA1). This is the place where we added detection code for entering UF2 mode mentioned by above methods. 

Unfortunately ESP32S2 doesn't have a dedicated reset pin, but rather using [power pin (CHIP_PU) as way to reset](https://github.com/espressif/esp-idf/issues/494#issuecomment-291921540). This makes it impossible to use any RAM (internal and PSRAM) to store the temporary double reset magic. However, using an resistor and capacitor attached to a GPIO, we can implement a 1-bit memory to hold pin value long enough for double reset detection.

**TODO** guide and schematic as well as note for resistor + capacitor.

## UF2 Application as 3rd stage Bootloader 

UF2 is actually a **factory application** which is pre-flashed on the board along with 2nd bootloader and partition table. When there is no user application or 2nd bootloader "double reset alternative" decide to load uf2. Therefore it is technically 3rd stage bootloader.

It will show up as mass storage device and accept uf2 file to write to user application partition. UF2 bootloader will always write/update firmware to **ota_0** partition, since the actual address is dictated by **partitions.csv**, uf2 file base address **MUST** be 0x00, the uf2 will parse the partition table and start writing from address of ota_0. It also makes sure there is no out of partition writing.

After complete writing, uf2 will set the ota0 as bootable and reset, and the application should be running in the next boot.

NOTE: uf2 bootloader, customized 2nd bootloader and partition table can be overwritten by ROM DFU and/or UART uploading. Especially the `idf.py flash` which will upload everything from the user application project. It is advisable to upload only user application only with `idf.py app-flash` and leave other intact provided the user partition table matched this uf2 partition.

~~**TODO** Since uf2 is full-fledged application, we can also present a second MassStorage LUN for user FAT if it is present as way to edit the corrupted script/data.~~

## Partition

The following partition isn't final yet, current build without optimization and lots of debug is around 100 KB. Since IDF requires application type must be 64KB aligned, uf2 is best with size of 64KB, we will try to see if we could fit  https://github.com/microsoft/uf2/blob/master/hf2.md and https://github.com/microsoft/uf2/blob/master/cf2.md within 64KB.

UF2 only uses `ota_0` ~~and `user_fs` (additional LUN)~~, user application can change partition table (e.g increase ota_0 size, re-arrange layout/address) but should not overwrite the uf2 part. If an complete re-design partition is required, `uf2_bootloader.bin` and the `modified 2nd_stage_bootloader.bin` should be included as part of user combined binary for flash command.

```
# Name   , Type , SubType ,   Offset , Size   , Flags
otadata  , data , ota     ,   0xd000 , 0x2000 ,
phy_init , data , phy     ,   0xf000 , 0x1000 ,
ota_0    , 0    , ota_0   ,  0x10000 , 512K   ,
ota_1    , 0    , ota_1   ,  0x90000 , 512K   ,
nvs      , data , nvs     , 0x110000 , 0x6000 ,

# temporarily increased size for debugging, optimize later
uf2      , app  , factory ,  , 512K  ,
user_fs  , data , fat     , 0x200000 , 2M     ,
```

## Build and Flash

### Build 

Use `-DBOARD=` to specify target board

```
idf.py -DBOARD=espressif_saola_1_wrover build
```

### Flash with UART

```
idf.py -DBOARD=espressif_saola_1_wrover flash
```

### Flash with ROM USB DFU

TODO: update later


**FIXME**: There is a bug with UART baudrate = 115200, the board will not enumerate, but it works just fine with baudrate of 921600. This is possibly a race condition somewhere to fix. This is observed with ubuntu 18.04
 