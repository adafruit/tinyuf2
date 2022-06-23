# TinyUF2 for STM32F4

TinyUF2 reserved 64KB for compatible with existing application e.g CiruitPython, even though TinyUF2 actual binary size is much smaller (less than 32KB). Therefore application should start at `0x08010000`

Note: if you are using ST cmsis [Template/system_stm32f4xx.c](https://github.com/STMicroelectronics/cmsis_device_f4/blob/master/Source/Templates/system_stm32f4xx.c) in your application project, make sure you have at least version v2.6.6, older version may set your vector table (SCB->VTOR) to **incorrectly value** of 0x08000000.

To create a UF2 image from a .bin file, either use family option `STM32F4` or its magic number as follows:

From hex

```
uf2conv.py -c -f 0x57755a57 firmware.hex
uf2conv.py -c -f STM32F4 firmware.hex
```

From bin

```
uf2conv.py -c -b 0x08010000 -f STM32F4 firmware.bin
uf2conv.py -c -b 0x08010000 -f 0x57755a57 firmware.bin
```
