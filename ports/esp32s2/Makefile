# Espressif IDF use CMake build system, this add wrapper target to call idf.py

.PHONY: all build clean flash monitor erase
.DEFAULT_GOAL := all

# Build directory
BUILD = _build/build-$(BOARD)

all:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) build

build: all

clean:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) clean

flash:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) flash

erase:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) erase_flash

monitor:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) monitor

_bin/$(BOARD):
	@mkdir -p $@

copy-bin: _bin/$(BOARD)
	@cp $(BUILD)/bootloader/bootloader.bin $<
	@cp $(BUILD)/partition_table/partition-table.bin $<
	@cp $(BUILD)/ota_data_initial.bin $<
	@cp $(BUILD)/tinyuf2.bin $<
