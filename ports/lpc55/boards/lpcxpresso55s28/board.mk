MCU = LPC55S28
MCU_CORE = $(MCU)
CFLAGS += -DCPU_LPC55S28JBD100

# For flash-pyocd
PYOCD_TARGET = $(MCU)

# For flash-jlink target
JLINK_DEVICE = LPC55S28JBD100

flash: flash-pyocd
erase: flash-pyocd
