MCU = K32L2B31A

CFLAGS += \
  -DCPU_K32L2B31VLH0A \
  -DCFG_TUSB_MCU=OPT_MCU_K32L2BXX

SRC_C += \
	$(SDK_DIR)/drivers/dma/fsl_dma.c \
	$(SDK_DIR)/drivers/dmamux/fsl_dmamux.c \
	$(SDK_DIR)/drivers/tpm/fsl_tpm.c \
  $(BOARD_DIR)/kuiic_rgb.c

INC += \
	$(TOP)/$(SDK_DIR)/drivers/dma \
	$(TOP)/$(SDK_DIR)/drivers/dmamux \
	$(TOP)/$(SDK_DIR)/drivers/tpm


LD_FNAME = K32L2B31xxxxA_flash.ld

DBL_TAP_REG_ADDR = 0x4003D008

# For flash-pyocd target
PYOCD_TARGET = K32L2B3

# flash using pyocd
flash: flash-pyocd
erase: erase-jlink
