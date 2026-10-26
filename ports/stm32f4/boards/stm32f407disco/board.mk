CFLAGS += \
  -DSTM32F407xx \
  -DHSE_VALUE=8000000U

SRC_S += \
  $(ST_CMSIS)/Source/Templates/gcc/startup_stm32f407xx.s

# For flash-jlink target
JLINK_DEVICE = stm32f407vg

flash: flash-stlink
erase: erase-stlink
