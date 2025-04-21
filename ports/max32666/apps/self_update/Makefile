PORT = max32666
OUTNAME = self-update-$(BOARD)

BUILD_APPLICATION = 1
BUILD_NO_TINYUSB = 1

CFLAGS += -DTINYUF2_SELF_UPDATE

include ../../../make.mk
include ../../port.mk

SRC_C += \
	apps/self_update/self_update.c \
	$(TOP)/$(PORT_DIR)/apps/self_update/_build/bootloader_bin.c \

include ../../../rules.mk


uf2: $(BUILD)/$(OUTNAME).uf2

$(BUILD)/$(OUTNAME).uf2: $(BUILD)/$(OUTNAME).hex
	@echo CREATE $@
	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py -f $(UF2_FAMILY_ID) -c -o $@ $^
