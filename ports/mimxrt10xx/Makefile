PORT = mimxrt10xx

#-------------- Cross Compiler  ------------
CROSS_COMPILE = arm-none-eabi-

CC = $(CROSS_COMPILE)gcc
CXX = $(CROSS_COMPILE)g++
OBJCOPY = $(CROSS_COMPILE)objcopy
SIZE = $(CROSS_COMPILE)size
MKDIR = mkdir
SED = sed
CP = cp
RM = rm

include ../make.mk

MCU_DIR = lib/nxp/sdk/devices/$(MCU)
LD_FILE ?= $(PORT_DIR)/linker/$(MCU)xxxxx_flexspi_nor.ld
LDFLAGS += -L"$(TOP)/$(PORT_DIR)/linker"

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
	$(addprefix $(CURRENT_PATH)/, $(wildcard *.c)) \
	lib/tinyusb/src/portable/nxp/transdimension/dcd_transdimension.c \
	$(MCU_DIR)/system_$(MCU).c \
	$(MCU_DIR)/project_template/clock_config.c \
	$(MCU_DIR)/drivers/fsl_clock.c \
	$(MCU_DIR)/drivers/fsl_gpio.c \
	$(MCU_DIR)/drivers/fsl_common.c \
	$(MCU_DIR)/drivers/fsl_ocotp.c \
	$(MCU_DIR)/drivers/fsl_cache.c \
	$(MCU_DIR)/drivers/fsl_flexspi.c \
	$(MCU_DIR)/drivers/fsl_lpuart.c

SRC_S += $(MCU_DIR)/gcc/startup_$(MCU).S

# Port include
INC += \
	$(TOP)/$(MCU_DIR)/../../CMSIS/Include \
	$(TOP)/$(MCU_DIR) \
	$(TOP)/$(MCU_DIR)/drivers \
	$(TOP)/$(MCU_DIR)/xip \
	$(TOP)/$(MCU_DIR)/project_template

include ../rules.mk
