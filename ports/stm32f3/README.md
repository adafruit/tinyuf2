# TinyUF2 for STM32F3

TinyUF2 reserved 16KB therefore application should start at `0x08004000`

To create a UF2 image from a .bin file, either use family option `STM32F3` or its magic number as follows:

From hex

```
uf2conv.py -c -f 0x6b846188 firmware.hex
uf2conv.py -c -f STM32F3 firmware.hex
```

From bin

```
uf2conv.py -c -b 0x08004000 -f STM32F3 firmware.bin
uf2conv.py -c -b 0x08004000 -f 0x6b846188 firmware.bin
```
