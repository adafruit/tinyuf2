CROSS_COMPILE = arm-none-eabi-
PORT = mimxrt10xx
OUTNAME = erase_firmware-$(BOARD)

# skip src and tinyusb files
BUILD_APPLICATION = 1
BUILD_NO_TINYUSB = 1

include ../../../make.mk
include $(TOP)/$(PORT_DIR)/port.mk

LD_FILES ?= $(PORT_DIR)/linker/$(MCU)_ram.ld $(PORT_DIR)/apps/memory.ld $(PORT_DIR)/linker/common.ld

SRC_C += apps/erase_firmware/erase_firmware.c

INC += $(TOP)/src

include $(TOP)/ports/rules.mk

APPLICATION_ADDR = 0x6000C000

$(BUILD)/$(OUTNAME).uf2: $(BUILD)/$(OUTNAME)-textonly.bin
	@echo CREATE $@
	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py -f $(UF2_FAMILY_ID) -b $(APPLICATION_ADDR) -c -o $@ $<

$(BUILD)/$(OUTNAME)-textonly.bin: $(BUILD)/$(OUTNAME).elf
	@echo CREATE $@
	@$(OBJCOPY) -O binary -R .flash_config -R .ivt $^ $@

#-------------- Artifacts --------------
# TODO refactor/remove later
$(BIN):
	@$(MKDIR) -p $@

all: $(BIN)
all: $(BUILD)/$(OUTNAME).uf2
	$(CP) $< $(BIN)
