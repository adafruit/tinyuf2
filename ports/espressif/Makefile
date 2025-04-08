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

UF2_FAMILY_ID_esp32s2 = 0xbfdd4eee
UF2_FAMILY_ID_esp32s3 = 0xc47e5767

BOARD_CMAKE := $(file < boards/$(BOARD)/board.cmake)
ifneq ($(findstring esp32s2,$(BOARD_CMAKE)),)
	IDF_TARGET = esp32s2
else
ifneq ($(findstring esp32s3,$(BOARD_CMAKE)),)
	IDF_TARGET = esp32s3
endif
endif

all:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) build

build: all

fullclean:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) fullclean
	@rm -rf $(BIN)
	@rm -rf $(SELF_BUILD)

app bootloader clean flash bootloader-flash app-flash erase-flash monitor dfu-flash dfu size size-components size-files:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) $(SERIAL_OPT) $@

combined.bin: $(BUILD)/combined.bin

$(BUILD)/combined.bin: app
	cd $(BUILD); \
	esptool.py --chip $(IDF_TARGET) merge_bin --output combined.bin $(strip $(file < $(BUILD)/flash_args))

combined-flash: $(BUILD)/combined.bin
	esptool.py --chip $(IDF_TARGET) write_flash 0x0 $<

#-------------- Self Update --------------
# Self_update is a sub/external project, will be built by cmake's all target
SELF_BUILD = ${BUILD}/self_update

#-------------- Artifacts --------------
$(BIN):
	@mkdir -p $@

# get the partition csv from sdkconfig
PARTITION_CSV := $(strip $(foreach csv,$(wildcard partitions-*.csv),$(findstring $(csv),$(file < boards/$(BOARD)/sdkconfig))))

copy-artifact: $(BIN) all $(BUILD)/combined.bin
	@cp $(BUILD)/bootloader/bootloader.bin $<
	@cp $(BUILD)/partition_table/partition-table.bin $<
	@cp $(BUILD)/ota_data_initial.bin $<
	@cp $(BUILD)/tinyuf2.bin $<
	@cp $(BUILD)/combined.bin $<
	@cp $(SELF_BUILD)/update-tinyuf2.uf2 $<
	@cp $(PARTITION_CSV) $<
