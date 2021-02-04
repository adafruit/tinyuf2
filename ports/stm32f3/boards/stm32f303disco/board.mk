CFLAGS += \
  -DSTM32F303xC \
  -DHSE_VALUE=8000000U

SRC_S += \
  $(ST_CMSIS)/Source/Templates/gcc/startup_stm32f303xc.s

# For flash-jlink target
JLINK_DEVICE = stm32f303vc

flash: flash-stlink
erase: erase-stlink
