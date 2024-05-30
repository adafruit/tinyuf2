# List of git submodules that is included as part of the UF2 version
GIT_SUBMODULES = tinyusb

include ../make.mk

# inline port details
UF2_FAMILY_ID = 0x7f83e793
CROSS_COMPILE = arm-none-eabi-

SDK_DIR = lib/mcu/nxp/mcux-sdk
MCU_DIR = $(SDK_DIR)/devices/$(MCU)
CMSIS_5 = lib/CMSIS_5

# Port Compiler Flags
CFLAGS += \
  -flto \
  -mthumb \
  -mabi=aapcs \
  -mcpu=cortex-m0plus

# suppress warning caused by vendor mcu driver
CFLAGS += -Wno-error=cast-align -Wno-error=unused-parameter

# Port source
SRC_C += \
	$(MCU_DIR)/system_$(MCU).c \
	$(MCU_DIR)/drivers/fsl_clock.c \
	$(SDK_DIR)/drivers/gpio/fsl_gpio.c \
	$(SDK_DIR)/drivers/flash/fsl_ftfx_controller.c \
	$(SDK_DIR)/drivers/flash/fsl_ftfx_flash.c \
	$(SDK_DIR)/drivers/flash/fsl_ftfx_cache.c \
	$(SDK_DIR)/drivers/flash/fsl_ftfx_flexnvm.c \
	$(SDK_DIR)/drivers/lpuart/fsl_lpuart.c \
	$(PORT_DIR)/clock_config.c \
	$(PORT_DIR)/boards.c \
	$(PORT_DIR)/board_flash.c

ifndef BUILD_NO_TINYUSB
SRC_C += lib/tinyusb/src/portable/nxp/khci/dcd_khci.c
endif

SRC_S += $(MCU_DIR)/gcc/startup_$(MCU).S

# Port include
INC += \
  $(TOP)/$(PORT_DIR) \
	$(TOP)/$(BOARD_DIR) \
	$(TOP)/$(CMSIS_5)/CMSIS/Core/Include \
	$(TOP)/$(MCU_DIR) \
	$(TOP)/$(MCU_DIR)/drivers \
	$(TOP)/$(SDK_DIR)/drivers/smc \
	$(TOP)/$(SDK_DIR)/drivers/rtc \
	$(TOP)/$(SDK_DIR)/drivers/common \
	$(TOP)/$(SDK_DIR)/drivers/gpio \
	$(TOP)/$(SDK_DIR)/drivers/port \
	$(TOP)/$(SDK_DIR)/drivers/lpuart \
	$(TOP)/$(SDK_DIR)/drivers/flash

LD_FILES ?= $(MCU_DIR)/gcc/$(LD_FNAME)

include ../rules.mk

#-------------- Self-update  --------------
self-update:
	@echo "not implemented yet"
