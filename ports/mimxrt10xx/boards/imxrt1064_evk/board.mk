MCU = MIMXRT1064
CFLAGS += -DCPU_MIMXRT1064DVL6A

# For flash-jlink target
JLINK_DEVICE = MIMXRT1064xxx6A

# For flash-pyocd target
PYOCD_TARGET = mimxrt1064

# flash using pyocd
flash: flash-pyocd-bin
erase: erase-pyocd
