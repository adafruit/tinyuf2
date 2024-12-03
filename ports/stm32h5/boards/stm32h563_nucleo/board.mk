LD_FLASH_BOOT_SIZE = 32K
LD_RAM_SIZE = 640K
CFLAGS += \
  -DSTM32H563xx \
  -DHSE_VALUE=8000000 \

SRC_S += \
	$(ST_CMSIS)/Source/Templates/gcc/startup_stm32h563xx.s

# For flash-jlink target
JLINK_DEVICE = stm32h563zi

flash: flash-dfu-util
erase: erase-dfu-util
