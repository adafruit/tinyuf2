Remember when creating the uf2 file that the family_id and base address are specified as follows:
uf2conv.py -o stm32f411blackpill-app.uf2 -b 0x08010000 -f 0x57755a57 stm32f411blackpill-app.bin
uf2conv.py -o stm32f411blackpill-app.uf2 -b 0x08010000 -f STM32F4    stm32f411blackpill-app.bin
