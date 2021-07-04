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
# not implemented
SELF_DIR = apps/self-update

$(SELF_DIR)/bootloader_bin.c:	$(BUILD)/$(OUTNAME).bin
	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py --carray $^ -o $@

self-update: $(SELF_DIR)/bootloader_bin.c
	make -C apps/self-update BOARD=$(BOARD) self-update
	@rm $^
