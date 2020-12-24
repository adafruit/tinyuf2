MCU = LPC55S69
CFLAGS += -DCPU_LPC55S69JBD100_cm33_core0
SRC_S +=

# For flash-pyocd
PYOCD_TARGET = LPC55S69

# For flash-jlink target
JLINK_DEVICE = LPC55S69

flash: flash-pyocd
erase: flash-pyocd
