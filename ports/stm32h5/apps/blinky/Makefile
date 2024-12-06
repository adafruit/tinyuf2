PORT = stm32h5
OUTNAME = blinky-$(BOARD)

BUILD_APPLICATION = 1
BUILD_NO_TINYUSB = 1

include ../../../make.mk
include ../../port.mk

SRC_C += \
	apps/blinky/blinky.c \

include ../../../rules.mk

uf2: $(BUILD)/$(OUTNAME).uf2

$(BUILD)/$(OUTNAME).uf2: $(BUILD)/$(OUTNAME).hex
	@echo CREATE $@
	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py -f $(UF2_FAMILY_ID) -c -o $@ $^
