PORT = mimxrt10xx

# skip bootloader src
BUILD_APPLICATION = 1

include ../../../make.mk
include $(TOP)/$(PORT_DIR)/port.mk

LD_FILES ?= $(PORT_DIR)/linker/$(MCU)_ram.ld $(PORT_DIR)/apps/memory.ld $(PORT_DIR)/linker/common.ld

include $(TOP)/ports/rules.mk

APPLICATION_ADDR = 0x6000C000

# self-update uf2 file
uf2: $(BUILD)/$(OUTNAME).uf2

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

flash-app: $(BUILD)/$(OUTNAME)-textonly.bin
	pyocd flash -t $(PYOCD_TARGET) -a $(APPLICATION_ADDR) $<
	pyocd reset -t $(PYOCD_TARGET)

# UF2_BOOT_MOUNT_PATH is defined in board.mk
flash-uf2: $(BUILD)/$(OUTNAME).uf2
	$(CP) $< $(UF2_BOOT_MOUNT_PATH)/
