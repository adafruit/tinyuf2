# List of git submodules that is included as part of the UF2 version
GIT_SUBMODULES = tinyusb

include ../make.mk
include port.mk
include ../rules.mk

#------------------------------------------
# Self-update
#------------------------------------------
self-update: $(BUILD)/$(OUTNAME).bin
	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py --carray $^ -o apps/self_update/_build/bootloader_bin.c
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/self_update uf2

self-update-clean:
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/self_update clean

#---------- Erase Firmware ----------
# Compile apps/erase_firmware/erase_firmware.c
erase-firmware:
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/erase_firmware uf2

erase-firmware-clean:
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/erase_firmware clean

#---------- Blinky ----------
# Compile apps/blinky/blinky.c
blinky:
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/blinky uf2

blinky-clean:
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/blinky clean
