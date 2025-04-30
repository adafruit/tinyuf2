CFLAGS += \
  -DSTM32G474xx \
  -DHSE_VALUE=4000000U

SRC_S += \
	$(ST_CMSIS)/Source/Templates/gcc/startup_stm32g474xx.s


# For flash-jlink target
JLINK_DEVICE = stm32g474ce

flash: flash-jlink
erase: erase-jlink
