MCU = MIMXRT1042
CFLAGS += -DCPU_MIMXRT1042XJM5B

# For flash-jlink target
JLINK_DEVICE = MIMXRT1042xxx5B

# For flash-pyocd target
PYOCD_TARGET = mimxrt1042

# flash using pyocd
flash: flash-pyocd-bin
erase: erase-pyocd
