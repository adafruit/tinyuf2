MCU = MIMXRT1062
CFLAGS += -DCPU_MIMXRT1062DVL6A

# For flash-pyocd target
PYOCD_TARGET = mimxrt1060

# Convert the .bin file to a teensy loadable .hex file
$(BUILD)/$(OUTNAME)-loadable.hex: $(BUILD)/$(OUTNAME).bin
	$(OBJCOPY) -I binary -O ihex --change-addresses 0x60000000 $< $@

# Add the teensy loadable hex file to the 'all' target
all: $(BUILD)/$(OUTNAME)-loadable.hex

# Flash using the teensy loader
flash: $(BUILD)/$(OUTNAME)-loadable.hex
	@echo "Waiting for teensy to attach.  If you haven't already, make sure to press the teensy button, and make sure you don't have the teensy app running in auto mode."
	teensy_loader_cli -w --mcu TEENSY40 $<
