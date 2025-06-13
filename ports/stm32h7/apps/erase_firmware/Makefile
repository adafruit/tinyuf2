OUTNAME = erase_firmware-$(BOARD)

# skip tinyusb
BUILD_NO_TINYUSB = 1

SRC_C += \
  apps/erase_firmware/src/erase_firmware.c \
	$(PORT_DIR)/boards.c \
	$(PORT_DIR)/board_flash.c \
	$(PORT_DIR)/board_irq.c \

INC += \
	$(TOP)/src \

include ../app.mk
