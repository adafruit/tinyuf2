OUTNAME = erase_firmware-$(BOARD)

# skip tinyusb
BUILD_NO_TINYUSB = 1

SRC_C += \
	$(PORT_DIR)/boards.c \
	apps/erase_firmware/erase_firmware.c

INC += $(TOP)/src

include ../app.mk
