OUTNAME = erase_firmware-$(BOARD)

# skip tinyusb
BUILD_NO_TINYUSB = 1

SRC_C += \
	apps/erase_firmware/erase_firmware.c \
	$(TOP)/$(PORT_DIR)/boards.c \
	$(TOP)/$(PORT_DIR)/board_flash.c \
	$(TOP)/$(PORT_DIR)/board_irq.c \

ifeq ($(QSPI_FLASH),W25Qx_QSPI)
SRC_C += \
    $(TOP)/$(PORT_DIR)/components/w25qxx/w25qxx.c \
    $(TOP)/$(PORT_DIR)/components/w25qxx/w25qxx_qspi.c
endif

ifeq ($(QSPI_FLASH),IS25LP064A)
SRC_C += \
  $(TOP)/$(PORT_DIR)/components/is25lp064a/is25lp064a_qspi.c
endif

INC += \
	$(TOP)/src \

include ../app.mk
