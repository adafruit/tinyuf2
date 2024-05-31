# List of git submodules that is included as part of the UF2 version
GIT_SUBMODULES = tinyusb

include ../make.mk
include port.mk
include ../rules.mk

#------------------------------------------
# Self-update
#------------------------------------------

# directory containing Makefile for building update app
SELF_DIR = apps/self_update

#$(SELF_DIR)/bootloader_bin.c:	$(BUILD)/$(OUTNAME).bin
#	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py --carray $^ -o $@
#
## remove bootloader_bin.c at the end to force re-generate each time
#self-update: $(SELF_DIR)/bootloader_bin.c
#	make -C $(SELF_DIR) BOARD=$(BOARD) LOG=$(LOG) LOGGER=$(LOGGER) self-update
#	@rm -f $^

self-update:
	@echo "not implemented yet"
