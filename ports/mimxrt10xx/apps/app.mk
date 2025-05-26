PORT = mimxrt10xx

# skip bootloader src
BUILD_APPLICATION = 1

include ../../../make.mk
include $(TOP)/$(PORT_DIR)/port.mk

LD_FILES ?= $(PORT_DIR)/linker/$(MCU)_ram.ld $(PORT_DIR)/linker/app.ld $(PORT_DIR)/linker/common.ld

include $(TOP)/ports/rules.mk

# self-update uf2 file
uf2: $(BUILD)/$(OUTNAME).uf2

$(BUILD)/$(OUTNAME).uf2: $(BUILD)/$(OUTNAME).hex
	@echo CREATE $@
	$(UF2CONV_PY) -f $(UF2_FAMILY_ID) -c -o $@ $<

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

flash-app: $(BUILD)/$(OUTNAME).hex
	pyocd flash -t $(PYOCD_TARGET) $<
	pyocd reset -t $(PYOCD_TARGET)

# flash by copying uf2
flash-uf2: $(BUILD)/$(OUTNAME).uf2
	$(UF2CONV_PY) -f $(UF2_FAMILY_ID) --deploy $<
