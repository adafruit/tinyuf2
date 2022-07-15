MCU = MIMXRT1021
CFLAGS += -DCPU_MIMXRT1021DAG5A

# For flash-jlink target
JLINK_DEVICE = MIMXRT1021DAG5A

# For flash-pyocd target
PYOCD_TARGET = mimxrt1020

# flash using pyocd
flash: flash-pyocd-bin
erase: erase-pyocd
