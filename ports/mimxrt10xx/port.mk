UF2_FAMILY_ID = 0x4fb2d5bd

MCU_DIR = lib/nxp/sdk/devices/$(MCU)

# Port Compiler Flags
CFLAGS += \
  -mthumb \
  -mabi=aapcs \
  -mcpu=cortex-m7 \
  -mfloat-abi=hard \
  -mfpu=fpv5-d16 \
  -D__ARMVFP__=0 -D__ARMFPV5__=0 \
  -DXIP_EXTERNAL_FLASH=1 \
  -DXIP_BOOT_HEADER_ENABLE=1 \
  -DCFG_TUSB_MCU=OPT_MCU_MIMXRT10XX
  
# mcu driver cause following warnings
CFLAGS += -Wno-error=unused-parameter

# Port source
SRC_C += \
	$(PORT_DIR)/boards.c \
	$(MCU_DIR)/system_$(MCU).c \
	$(MCU_DIR)/project_template/clock_config.c \
	$(MCU_DIR)/drivers/fsl_clock.c \
	$(MCU_DIR)/drivers/fsl_gpio.c \
	$(MCU_DIR)/drivers/fsl_common.c \
	$(MCU_DIR)/drivers/fsl_ocotp.c \
	$(MCU_DIR)/drivers/fsl_cache.c \
	$(MCU_DIR)/drivers/fsl_pwm.c \
	$(MCU_DIR)/drivers/fsl_xbara.c \
	$(MCU_DIR)/drivers/fsl_lpuart.c

ifndef BUILD_NO_TINYUSB
SRC_C += lib/tinyusb/src/portable/nxp/transdimension/dcd_transdimension.c
endif

SRC_S += $(MCU_DIR)/gcc/startup_$(MCU).S

# Port include
INC += \
  $(TOP)/$(PORT_DIR) \
  $(TOP)/$(BOARD_DIR) \
	$(TOP)/$(MCU_DIR)/../../CMSIS/Include \
	$(TOP)/$(MCU_DIR) \
	$(TOP)/$(MCU_DIR)/drivers \
	$(TOP)/$(MCU_DIR)/xip \
	$(TOP)/$(MCU_DIR)/project_template
