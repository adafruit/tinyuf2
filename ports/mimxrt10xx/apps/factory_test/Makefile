OUTNAME = factory_test-$(BOARD)

SRC_C += \
	$(PORT_DIR)/boards.c \
	$(CURRENT_PATH)/main.c \
	$(CURRENT_PATH)/arduino.c \
	$(CURRENT_PATH)/wifi_scan.c \
	$(CURRENT_PATH)/usb_descriptors.c \
	$(SDK_DIR)/drivers/adc_12b1msps_sar/fsl_adc.c \
	$(SDK_DIR)/drivers/common/fsl_common_arm.c \

INC += \
	$(TOP)/$(CURRENT_PATH) \
	$(TOP)/src \
	$(TOP)/$(SDK_DIR)/drivers/adc_12b1msps_sar \

ifeq ($(BOARD),metro_m7_1011)
include ../app.mk

else

all:
	@echo This app is only board only built for metro_m7_1011

endif
