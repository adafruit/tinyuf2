# TinyUF2 for STM32H5

TinyUF2 occupies 24KB. Therefore application should start at `0x08006000`

To create a UF2 image from a .bin file, either use family option `STM32H5` or its magic number as follows:

From hex

```
uf2conv.py -c -f 0x4e8f1c5d firmware.hex
uf2conv.py -c -f STM32H5 firmware.hex
```

From bin

```
uf2conv.py -c -b 0x08010000 -f STM32H5 firmware.bin
uf2conv.py -c -b 0x08010000 -f 0x4e8f1c5d firmware.bin
```
