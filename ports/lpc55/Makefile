# List of git submodules that is included as part of the UF2 version
GIT_SUBMODULES = nxp/mcux-sdk sct_neopixel tinyusb

include ../make.mk
include port.mk

SRC_C += \
  $(PORT_DIR)/boards.c

ifndef BUILD_NO_TINYUSB
SRC_C += lib/tinyusb/src/portable/nxp/lpc_ip3511/dcd_lpc_ip3511.c
endif

LD_FILES ?= $(MCU_DIR)/gcc/$(MCU_CORE)_flash.ld

include ../rules.mk

#-------------- Self-update  --------------

SELF_DIR = apps/self-update

$(SELF_DIR)/bootloader_bin.c:	$(BUILD)/$(OUTNAME).bin
	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py --carray $^ -o $@

self-update: $(SELF_DIR)/bootloader_bin.c
	make -C apps/self-update BOARD=$(BOARD) self-update
	@rm $^

ifdef abc
SELF_CFLAGS  = $(CFLAGS) -DTINYUF2_SELF_UPDATE
SELF_LDFLAGS = $(LDFLAGS)
SELF_LD_FILES ?= $(LD_FILES)
SELF_ASFLAGS = $(ASFLAGS)

include ../self_update.mk

# self-update uf2 file
$(SELF_BUILD_OBJ)/$(SELF_OUTNAME).uf2: $(SELF_BUILD_OBJ)/$(SELF_OUTNAME).hex
	@echo CREATE $@
	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py -f $(UF2_FAMILY_ID) -c -o $@ $^

$(SELF_BUILD_OBJ)/$(SELF_OUTNAME).hex: $(SELF_BUILD_OBJ)/$(SELF_OUTNAME).elf
	@echo CREATE $@
	@$(OBJCOPY) -O ihex $^ $@

# required for self-update elf compile
$(SELF_BUILD_OBJ)/self_update/$(OUTNAME).c:
	@echo "const unsigned long bindata_len = 1;" > $@
	@echo "const unsigned char bindata[] __attribute__((aligned(16))) = { 0 };" >> $@
	#$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py --carray $^ -o $@

endif
