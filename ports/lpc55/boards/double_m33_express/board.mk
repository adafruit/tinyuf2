MCU = LPC55S69
MCU_CORE = $(MCU)_cm33_core0
CFLAGS += -DCPU_LPC55S69JBD100_cm33_core0

SRC_C += lib/sct_neopixel/sct_neopixel.c

SELF_SRC_C += lib/sct_neopixel/sct_neopixel.c

INC += $(TOP)/lib/sct_neopixel

# For flash-pyocd
PYOCD_TARGET = $(MCU)

# For flash-jlink target
JLINK_DEVICE = LPC55S69_M33_0

flash: flash-pyocd
erase: flash-pyocd
