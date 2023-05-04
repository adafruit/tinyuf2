MCU = MIMXRT1052
CFLAGS += -DCPU_MIMXRT1052DVL6B

# For flash-jlink target
JLINK_DEVICE = MIMXRT1052xxxxB

# For flash-pyocd target
PYOCD_TARGET = mimxrt1052

# flash using pyocd
flash: flash-pyocd-bin
erase: erase-pyocd
