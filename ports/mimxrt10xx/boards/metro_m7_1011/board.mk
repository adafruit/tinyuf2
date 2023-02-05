MCU = MIMXRT1011
CFLAGS += -DCPU_MIMXRT1011DAE5A

# Modify mount path to your system if needed
UF2_BOOT_MOUNT_PATH = /media/$(USER)/METROM7BOOT

# For flash-jlink target
JLINK_DEVICE = MIMXRT1011DAE5A

# For flash-pyocd target
PYOCD_TARGET = mimxrt1010

# flash using pyocd
flash: flash-pyocd-bin
erase: erase-pyocd
