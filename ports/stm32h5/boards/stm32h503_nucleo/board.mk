CFLAGS += \
  -DSTM32H503xx

SRC_S += \
	$(ST_CMSIS)/Source/Templates/gcc/startup_stm32h503xx.s

# For flash-jlink target
JLINK_DEVICE = stm32h503rb

flash: flash-dfu-util
erase: erase-dfu-util
