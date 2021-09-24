# Espressif IDF use CMake build system, this add wrapper target to call idf.py

.PHONY: all build clean flash monitor erase
.DEFAULT_GOAL := all

# Set default python interpreters
PYTHON3 ?= python3

# Build directory
BUILD = _build/$(BOARD)
BIN = _bin/$(BOARD)
TOP = ../..

ifdef SERIAL
SERIAL_OPT = --port $(SERIAL)
endif

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
	idf.py -B$(BUILD) -DBOARD=$(BOARD) $(SERIAL_OPT) flash

bootloader-flash:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) $(SERIAL_OPT) bootloader-flash

app-flash:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) $(SERIAL_OPT) app-flash

erase:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) erase_flash

monitor:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) monitor

size-components:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) size-components

size-files:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) size-files

$(BUILD)/combined.bin: app
	UF2_OFFSET=`awk '{if(FNR==2)print $$1}' $(BUILD)/app-flash_args)`; \
	esptool.py --chip esp32s2 merge_bin --output $@ \
		0x1000 $(BUILD)/bootloader/bootloader.bin \
		0x8000 $(BUILD)/partition_table/partition-table.bin \
		0xe000 $(BUILD)/ota_data_initial.bin \
		$$UF2_OFFSET $(BUILD)/tinyuf2.bin

#-------------- Self Update --------------
SELF_BUILD = apps/self_update/$(BUILD)

$(SELF_BUILD)/update-tinyuf2.bin: app
	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py --carray $(BUILD)/tinyuf2.bin -o $(TOP)/apps/self_update/bootloader_bin.c
	idf.py -C apps/self_update/ -B$(SELF_BUILD) -DBOARD=$(BOARD) app
	@rm $(TOP)/apps/self_update/bootloader_bin.c

$(SELF_BUILD)/update-tinyuf2.uf2: $(SELF_BUILD)/update-tinyuf2.bin
	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py -f 0xbfdd4eee -b 0x0000 -c -o $@ $^

self-update: $(SELF_BUILD)/update-tinyuf2.uf2

#-------------- Artifacts --------------
$(BIN):
	@mkdir -p $@

copy-artifact: $(BIN) all self-update $(BUILD)/combined.bin
	@cp $(BUILD)/bootloader/bootloader.bin $<
	@cp $(BUILD)/partition_table/partition-table.bin $<
	@cp $(BUILD)/ota_data_initial.bin $<
	@cp $(BUILD)/tinyuf2.bin $<
	@cp $(BUILD)/combined.bin $<
	@cp $(SELF_BUILD)/update-tinyuf2.uf2 $<
