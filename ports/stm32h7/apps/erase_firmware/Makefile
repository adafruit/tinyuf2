OUTNAME = erase_firmware-$(BOARD)

# skip tinyusb
BUILD_NO_TINYUSB = 1

SRC_C += \
	apps/erase_firmware/erase_firmware.c \
	$(TOP)/$(PORT_DIR)/boards.c \
	$(TOP)/$(PORT_DIR)/board_flash.c \
	$(TOP)/$(PORT_DIR)/board_irq.c \
	$(TOP)/$(PORT_DIR)/components/w25qxx/w25qxx.c \
	$(TOP)/$(PORT_DIR)/components/w25qxx/w25qxx_qspi.c \

INC += \
	$(TOP)/src \

include ../app.mk
