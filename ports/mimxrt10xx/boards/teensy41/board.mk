MCU = MIMXRT1062
CFLAGS += -DCPU_MIMXRT1062DVL6A

# For flash-pyocd target
PYOCD_TARGET = mimxrt1060

# Flash using the teensy loader
flash: $(BUILD)/$(OUTNAME).hex
	@echo "Waiting for teensy to attach.  If you haven't already, make sure to press the teensy button, and make sure you don't have the teensy app running in auto mode."
	teensy_loader_cli -w --mcu TEENSY41 $<
