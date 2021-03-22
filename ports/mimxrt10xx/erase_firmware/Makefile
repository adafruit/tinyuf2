CROSS_COMPILE = arm-none-eabi-
PORT = mimxrt10xx
OUTNAME = erase_firmware-$(BOARD)

# skip src and tinyusb files
NO_TINYUF2_BUILD = 1

include ../../make.mk

include ../port.mk

LD_FILES ?= $(PORT_DIR)/linker/$(MCU)_ram.ld $(PORT_DIR)/erase_firmware/memory.ld $(PORT_DIR)/linker/common.ld

# Port Compiler Flags
CFLAGS += -DNO_TINYUF2_BUILD

# mcu driver cause following warnings
CFLAGS += -Wno-error=unused-parameter

# Port source
SRC_C += erase_firmware/erase_firmware.c

# Port include
INC += $(TOP)/src

include ../../rules.mk

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
ARTIFACT_DIR =

$(ARTIFACT_DIR):
	@$(MKDIR) -p $@

copy-artifact: $(ARTIFACT_DIR)
copy-artifact: $(BUILD)/$(OUTNAME).uf2
	@$(CP) $(BUILD)/$(OUTNAME).uf2 $(ARTIFACT_DIR)
