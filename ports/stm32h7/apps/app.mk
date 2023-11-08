PORT = stm32h7

# skip bootloader source for apps
BUILD_APPLICATION = 1

include ../../../make.mk
include $(TOP)/$(PORT_DIR)/port.mk

LD_FILES ?= \
	$(PORT_DIR)/linker/memory.ld \
	$(PORT_DIR)/linker/common.ld \
	$(PORT_DIR)/linker/$(MCU).ld

CFLAGS += \
	-DVECT_TAB_SRAM \
	-Wl,--defsym=RAMCODE=0

include $(TOP)/ports/rules.mk

# Load app into AXISRAM to run
APPLICATION_ADDR = 0x24000000

# Self-update uf2 file
uf2: $(BUILD)/$(OUTNAME).uf2

$(BUILD)/$(OUTNAME).uf2: $(BUILD)/$(OUTNAME)-ram.bin
	@echo CREATE $@
	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py -f $(UF2_FAMILY_ID) -b $(APPLICATION_ADDR) -c -o $@ $<

$(BUILD)/$(OUTNAME)-ram.bin: $(BUILD)/$(OUTNAME).elf
	@echo CREATE $@
	@$(OBJCOPY) -O binary  $^ $@
