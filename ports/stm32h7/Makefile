# List of git submodules that is included as part of the UF2 version
GIT_SUBMODULES = tinyusb uf2

include ../make.mk
include port.mk

LD_FILES ?= \
	$(PORT_DIR)/linker/memory.ld \
	$(PORT_DIR)/linker/common.ld \
	$(PORT_DIR)/linker/$(MCU).ld

SRC_C += \
	$(TOP)/$(PORT_DIR)/boards.c \
	$(TOP)/$(PORT_DIR)/board_flash.c \
	$(TOP)/$(PORT_DIR)/board_hmi.c \
	$(TOP)/$(PORT_DIR)/board_irq.c

include ../rules.mk

#---------- Self update ----------
# Compile apps/self_update/self_update.c
# This uf2 will be loaded into RAM
# TODO: this needs to build the actual uf2 binary first
self-update: $(BUILD)/$(OUTNAME).bin
	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py --carray $^ -o apps/self_update/_build/bootloader_bin.c
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/self_update uf2

self-update-clean:
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/self_update clean

#---------- Erase app ----------
# Compile apps/erase_firmware/erase_firmware.c
# This uf2 will be loaded into RAM
erase-app:
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/erase_firmware uf2

erase-app-clean:
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/erase_firmware clean
