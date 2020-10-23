MCU = MIMXRT1062
CFLAGS += -DCPU_MIMXRT1062DVL6A

# All source paths should be relative to the top level.
LD_FILE = $(MCU_DIR)/gcc/$(MCU)xxxxx_flexspi_nor.ld

# For flash-jlink target
JLINK_DEVICE = MIMXRT1062xxx6A

# flash by using teensy_loader_cli https://github.com/PaulStoffregen/teensy_loader_cli
# Make sure it is in your PATH 
flash: $(BUILD)/$(BOARD)-firmware.hex
	teensy_loader_cli --mcu=imxrt1062 -v -w $<
