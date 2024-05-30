MCU = K32L2B31A

CFLAGS += \
  -DCPU_K32L2B31VLH0A \
  -DCFG_TUSB_MCU=OPT_MCU_K32L2BXX

SRC_S +=

LD_FNAME = K32L2B31xxxxA_flash.ld

DBL_TAP_REG_ADDR = 0x4003D008

# For flash-pyocd target
PYOCD_TARGET = K32L2B3

# flash using pyocd
flash: flash-pyocd
erase: erase-jlink
