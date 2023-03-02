# Teensy 4.0 support

The [Teensy](https://www.pjrc.com/store/teensy40.html) is based on a MIMXRT1062, so is very similar to the imxrt1060_evk.

## Why tinyuf2 for the Teensy?

1. The primary purpose is if you want to use the OTG2 as the main USB interface to the teensy, instead of the built-in micro-USB connector (OTG1).  The teensy built-in bootloader does not operated with the secondary USB port.  For the Teensy 4.0 board, this isn't possible.
2. You're running non-arduino code and want to emulate other 1060 boards.


## Flashing
Initial flashing to load tinyUF2 must be done via the teensy CLI, or the teensy loader.  It must be done via the built-in micro USB connector.

1. Ensure that you *do* have the `teensy_loader_cli` program installed.  It's available [here](https://www.pjrc.com/teensy/loader_cli.html).
1. Connect a micro-USB cable directly to the teensy (as opposed to any secondary USB connector you might have on a daughter board)
1. press the teensy flash button.  Make sure that the teensy GUI does *NOT* come up.  The little red light adjacent to the USB connector should be on.
1. Flash the board:
```make BOARD=teensy40 flash```

At this point, the board should be flashed, the red light adjacent to the micro USB connector should be off, and the orange light next to the teensy button should be flashing intermittently.  There should also be a new disk that appears called TEENSY40BT.

## Building and flashing for the secondary USB port
This is not a valid configuration for the teensy 4.0 board because the second USB port isn't brought out to pads.
