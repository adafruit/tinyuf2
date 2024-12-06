LD_FLASH_BOOT_SIZE = 24K
LD_RAM_SIZE = 32K
CFLAGS += \
  -DSTM32H503xx \
  -DHSE_VALUE=24000000 \

SRC_S += \
	$(ST_CMSIS)/Source/Templates/gcc/startup_stm32h503xx.s

# For flash-jlink target
JLINK_DEVICE = stm32h503rb

flash: flash-dfu-util
erase: erase-dfu-util
