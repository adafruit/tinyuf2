OUTNAME = dfu_runtime-$(BOARD)

SRC_C += \
	$(PORT_DIR)/boards.c \
	$(CURRENT_PATH)/board_dfu_runtime.c \
	apps/dfu_runtime/src/main.c \
	apps/dfu_runtime/src/nonce.c \
	apps/dfu_runtime/src/usb_descriptors.c \

INC += \
	$(TOP)/apps/dfu_runtime/src \
	$(TOP)/src \

include ../app.mk
