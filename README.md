# Matrix Bootloader

This repo is a fork of [TinyUF2](https://github.com/adafruit/tinyuf2) for 203 System Mystrix Devices

Compared to the origonal bootloader, this fork added proper multi RGB pixel support, fastboot, device specific animations, and some Mystrix specific functions.


## Build for Mystrix:

  > run the export bat come with esp-idf first

    cd ports\espressif
    make BOARD=mystrix build

## Flash
  > Mystrix has to be in boot mode (boot pin shorted to ground) and connected to PC via ttl-usb convertpr


    make BOARD=mystrix build flash
