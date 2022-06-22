# List of git submodules that is included as part of the UF2 version
GIT_SUBMODULES = st/cmsis_device_f4 st/stm32f4xx_hal_driver tinyusb

include ../make.mk
include port.mk
include ../rules.mk

# flash using ROM bootloader
flash-dfu-util: $(BUILD)/$(OUTNAME).bin
	dfu-util -R -a 0 --dfuse-address 0x08000000 -D $<

#------------------------------------------
# Self-update
#------------------------------------------

# direction containing Makefile for building update app
SELF_DIR = apps/self_update

$(SELF_DIR)/bootloader_bin.c:	$(BUILD)/$(OUTNAME).bin
	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py --carray $^ -o $@

self-update: $(SELF_DIR)/bootloader_bin.c
	make -C $(SELF_DIR) BOARD=$(BOARD) self-update
	@rm $^
