CFLAGS += \
  -DSTM32F405xx \
  -DHSE_VALUE=12000000U

SRC_S += \
  $(ST_CMSIS)/Source/Templates/gcc/startup_stm32f405xx.s

# For flash-jlink target
JLINK_DEVICE = stm32f405rg

flash: flash-dfu-util
erase: erase-jlink
