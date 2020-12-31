MCU = MIMXRT1062
CFLAGS += -DCPU_MIMXRT1062DVL6A

# For flash-jlink target
JLINK_DEVICE = MIMXRT1062xxx6A

# For flash-pyocd target
PYOCD_TARGET = mimxrt1060

# flash using pyocd
flash: flash-pyocd-bin
erase: erase-pyocd
