# TinyUF2 for STM32L4

TinyUF2 reserved 64KB for compatible with eixisting application e.g ciruitpython, even though TinyUF2 actual binary size is much smaller (less than 32KB). Therefore application should start at `0x08010000`.

To create a UF2 image from a .bin file, either use family option `STM32L4` or its magic number as follows:

```
uf2conv.py -c -b 0x08010000 -f STM32L4 firmware.bin
uf2conv.py -c -b 0x08010000 -f 0x00ff6919 firmware.bin
```
