CFLAGS += \
  -DSTM32F401xC \
  -DHSE_VALUE=25000000U

SRC_S += \
	$(ST_CMSIS)/Source/Templates/gcc/startup_stm32f401xc.s

# For flash-jlink target
JLINK_DEVICE = stm32f401cc

flash: flash-dfu-util
erase: erase-dfu-util
