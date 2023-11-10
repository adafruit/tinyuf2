OUTNAME = esp32programmer-$(BOARD)

SRC_C += \
	$(PORT_DIR)/boards.c \
	$(CURRENT_PATH)/main.c \
	$(CURRENT_PATH)/usb_descriptors.c \

INC += \
	$(TOP)/$(CURRENT_PATH) \
	$(TOP)/src

ifeq ($(BOARD),metro_m7_1011)
include ../app.mk

else

all:
	@echo This board does not have ESP32 co-processor

endif
