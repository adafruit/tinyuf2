UF2_FAMILY_ID = 0x4fb2d5bd
CROSS_COMPILE = arm-none-eabi-

SDK_DIR = lib/mcu/nxp/mcux-sdk
MCU_DIR = $(SDK_DIR)/devices/$(MCU)
CMSIS_5 = lib/CMSIS_5

# Choose which USB port to use (default to USB0)
BOARD_TUD_RHPORT ?= 0

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
  -DCFG_TUSB_MCU=OPT_MCU_MIMXRT10XX \
  -DBOARD_TUD_RHPORT=$(BOARD_TUD_RHPORT)

# mcu driver cause following warnings
CFLAGS += -Wno-error=unused-parameter

# Port source
SRC_C += \
	$(MCU_DIR)/drivers/fsl_clock.c \
	$(SDK_DIR)/drivers/cache/armv7-m7/fsl_cache.c \
	$(SDK_DIR)/drivers/common/fsl_common.c \
	$(SDK_DIR)/drivers/igpio/fsl_gpio.c \
	$(SDK_DIR)/drivers/lpspi/fsl_lpspi.c \
	$(SDK_DIR)/drivers/lpuart/fsl_lpuart.c \
	$(SDK_DIR)/drivers/ocotp/fsl_ocotp.c \
	$(SDK_DIR)/drivers/pwm/fsl_pwm.c \
	$(SDK_DIR)/drivers/xbara/fsl_xbara.c \
	$(BOARD_DIR)/clock_config.c

ifeq ($(MCU),MIMXRT1176)
	SRC_C += $(MCU_DIR)/system_$(MCU)_cm7.c
	SRC_S += $(MCU_DIR)/gcc/startup_$(MCU)_cm7.S
else
	SRC_C += $(MCU_DIR)/system_$(MCU).c
	SRC_S += $(MCU_DIR)/gcc/startup_$(MCU).S
endif

# It seems that only RT1011 does not have ROM API
ifneq ($(MCU),MIMXRT1011)
SRC_C += $(MCU_DIR)/drivers/fsl_romapi.c
endif

ifeq ($(MCU),MIMXRT1176)
SRC_C += $(MCU_DIR)/drivers/fsl_dcdc.c \
	$(MCU_DIR)/drivers/fsl_anatop_ai.c \
	$(MCU_DIR)/drivers/fsl_pmu.c \
	$(SDK_DIR)/drivers/common/fsl_common_arm.c
endif

ifndef BUILD_NO_TINYUSB
SRC_C += lib/tinyusb/src/portable/chipidea/ci_hs/dcd_ci_hs.c
endif


# Port include
INC += \
  $(TOP)/$(PORT_DIR) \
  $(TOP)/$(BOARD_DIR) \
	$(TOP)/$(CMSIS_5)/CMSIS/Core/Include \
	$(TOP)/$(MCU_DIR) \
	$(TOP)/$(MCU_DIR)/xip \
	$(TOP)/$(MCU_DIR)/drivers \
	$(TOP)/$(SDK_DIR)/drivers/cache/armv7-m7 \
	$(TOP)/$(SDK_DIR)/drivers/common \
	$(TOP)/$(SDK_DIR)/drivers/igpio \
	$(TOP)/$(SDK_DIR)/drivers/lpspi \
	$(TOP)/$(SDK_DIR)/drivers/lpuart \
	$(TOP)/$(SDK_DIR)/drivers/ocotp \
	$(TOP)/$(SDK_DIR)/drivers/pwm \
	$(TOP)/$(SDK_DIR)/drivers/rtwdog \
	$(TOP)/$(SDK_DIR)/drivers/xbara \
	$(TOP)/$(SDK_DIR)/drivers/wdog01 \
