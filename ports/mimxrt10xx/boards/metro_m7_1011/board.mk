MCU = MIMXRT1011
CFLAGS += -DCPU_MIMXRT1011DAE5A

# For flash-jlink target
JLINK_DEVICE = MIMXRT1011DAE5A

# For flash-pyocd target
PYOCD_TARGET = mimxrt1010

# flash using pyocd
flash: flash-pyocd-bin
erase: erase-pyocd
