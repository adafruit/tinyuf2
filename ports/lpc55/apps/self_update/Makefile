PORT = lpc55
OUTNAME = update-tinyuf2-$(BOARD)

# skip bootloader src
BUILD_APPLICATION = 1

# skip tinyusb src
BUILD_NO_TINYUSB = 1

CFLAGS += -DTINYUF2_SELF_UPDATE

include ../../../make.mk
include ../../port.mk

SRC_C += \
	$(PORT_DIR)/boards.c \
	apps/self_update/self_update.c \
	$(CURRENT_PATH)/bootloader_bin.c

include ../../../rules.mk

self-update: $(BUILD)/$(OUTNAME).uf2

$(BUILD)/$(OUTNAME).uf2: $(BUILD)/$(OUTNAME).hex
	@echo CREATE $@
	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py -f $(UF2_FAMILY_ID) -c -o $@ $^
