CFLAGS +=
SRC_S +=

# For flash-jlink target
JLINK_DEVICE = stm32f405rg

flash: flash-jlink
erase: erase-jlink
