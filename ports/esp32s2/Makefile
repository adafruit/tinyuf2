# Espressif IDF use CMake build system, this add wrapper target to call idf.py

.PHONY: all build clean flash monitor erase
.DEFAULT_GOAL := all

# Set default python interpreters
PYTHON3 ?= python3

# Build directory
BUILD = _build/$(BOARD)
SELF_BUILD = self_update/$(BUILD)
BIN = _bin/$(BOARD)
TOP = ../..

all:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) build

build: all

app:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) app

clean:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) clean
	@rm -rf $(BIN)

fullclean:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) fullclean
	@rm -rf $(BIN)

flash:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) flash

bootloader-flash:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) bootloader-flash

app-flash:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) app-flash

erase:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) erase_flash

monitor:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) monitor

#-------------- Self Update --------------
$(SELF_BUILD)/update-tinyuf2.bin: app
	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py --carray $(BUILD)/tinyuf2.bin -o $(TOP)/self_update/bootloader_bin.c
	idf.py -C self_update/ -B$(SELF_BUILD) -DBOARD=$(BOARD) app
	@rm $(TOP)/self_update/bootloader_bin.c

$(SELF_BUILD)/update-tinyuf2.uf2: $(SELF_BUILD)/update-tinyuf2.bin
	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py -f 0xbfdd4eee -b 0x0000 -c -o $@ $^

self-update: $(SELF_BUILD)/update-tinyuf2.uf2

#-------------- Artifacts --------------
$(BIN):
	@mkdir -p $@

copy-artifact: $(BIN)
	@cp $(BUILD)/bootloader/bootloader.bin $<
	@cp $(BUILD)/partition_table/partition-table.bin $<
	@cp $(BUILD)/ota_data_initial.bin $<
	@cp $(BUILD)/tinyuf2.bin $<
	@cp $(SELF_BUILD)/update-tinyuf2.uf2 $<
