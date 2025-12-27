MCU = MIMXRT1176
CFLAGS += -DCPU_MIMXRT1176DVMAA_cm7
CFLAGS += -DMIMXRT117x_SERIES

# For flash-jlink target
JLINK_DEVICE = MIMXRT1176xxxA_M7

# For flash-pyocd target
PYOCD_TARGET = mimxrt1170_cm7

# flash using pyocd
flash: flash-pyocd-bin
erase: erase-pyocd
