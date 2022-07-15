MCU = MIMXRT1024
CFLAGS += -DCPU_MIMXRT1024DAG5A

# caused by system_MIMXRT1024.c:95:5
CFLAGS += -Wno-error=array-bounds

# For flash-jlink target
JLINK_DEVICE = MIMXRT1024DAG5A

# For flash-pyocd target
PYOCD_TARGET = mimxrt1024

# flash using pyocd
flash: flash-pyocd-bin
erase: erase-pyocd
