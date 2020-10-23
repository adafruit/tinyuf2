MCU = MIMXRT1021
CFLAGS += -DCPU_MIMXRT1021DAG5A

# All source paths should be relative to the top level.
LD_FILE = $(MCU_DIR)/gcc/$(MCU)xxxxx_flexspi_nor.ld

# For flash-jlink target
JLINK_DEVICE = MIMXRT1021DAG5A

# For flash-pyocd target
PYOCD_TARGET = mimxrt1020

# flash using pyocd
flash: flash-pyocd
