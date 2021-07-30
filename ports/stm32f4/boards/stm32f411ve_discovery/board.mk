CFLAGS += \
  -DSTM32F411xE \
  -DHSE_VALUE=8000000U

SRC_S += \
	$(ST_CMSIS)/Source/Templates/gcc/startup_stm32f411xe.s

# For flash-jlink target
JLINK_DEVICE = stm32f411ve

flash: flash-stlink
erase: erase-stlink
