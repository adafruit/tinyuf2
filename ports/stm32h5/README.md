# TinyUF2 for STM32H5

TinyUF2 occupies around 16Kb + 1KB for CF2 in flash. Since H5 has uniform sector size of 8KB, ideally we would have bootloader size set to 24KB. However, due to the fact that only H503 can protect/secure individual sector, the rest of H5 family (H52x, H56x) can only secure flash in 4-sector (group) unit. Therefore application should start at
- H503: `0x08006000`, boot size is 24KB
- H52x, H56x, H57x: `0x08008000`, boot size is 32KB
To create a UF2 image from a .bin file, either use family option `STM32H5` or its magic number as follows:

From hex

```
uf2conv.py -c -f 0x4e8f1c5d firmware.hex
uf2conv.py -c -f STM32H5 firmware.hex
```

From bin for H503

```
uf2conv.py -c -b 0x08006000 -f STM32H5 firmware.bin
uf2conv.py -c -b 0x08006000 -f 0x4e8f1c5d firmware.bin
```

From bin for H52x, H56x, H57x

```
uf2conv.py -c -b 0x08008000 -f STM32H5 firmware.bin
uf2conv.py -c -b 0x08008000 -f 0x4e8f1c5d firmware.bin
```
