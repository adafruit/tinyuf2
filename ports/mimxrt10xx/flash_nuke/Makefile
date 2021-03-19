CROSS_COMPILE = arm-none-eabi-
PORT = mimxrt10xx
OUTNAME = nuke-$(BOARD)

# skip src and tinyusb files
NO_TINYUF2_BUILD = 1

include ../../make.mk

MCU_DIR = lib/nxp/sdk/devices/$(MCU)
LD_FILES ?= $(PORT_DIR)/linker/$(MCU)_ram.ld $(PORT_DIR)/linker/memory.ld $(PORT_DIR)/linker/common.ld

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
  -DNO_TINYUF2_BUILD

# mcu driver cause following warnings
CFLAGS += -Wno-error=unused-parameter

# Port source
SRC_C += \
	$(addprefix $(CURRENT_PATH)/, $(wildcard *.c)) \
	$(PORT_DIR)/boards.c \
	$(subst $(TOP)/,,$(wildcard $(TOP)/$(BOARD_DIR)/*.c)) \
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

SRC_S += $(MCU_DIR)/gcc/startup_$(MCU).S

# Port include
INC += \
  $(TOP)/src \
  $(TOP)/$(PORT_DIR) \
  $(TOP)/$(BOARD_DIR) \
	$(TOP)/$(MCU_DIR)/../../CMSIS/Include \
	$(TOP)/$(MCU_DIR) \
	$(TOP)/$(MCU_DIR)/drivers \
	$(TOP)/$(MCU_DIR)/xip \
	$(TOP)/$(MCU_DIR)/project_template

include ../../rules.mk

#---------------------------------------------------------
# For flash-pyocd-bin target
#---------------------------------------------------------

FLASH_BIN_ADDR = $(UF2_$(MCU)_WRITE_ADDR)

UF2_MIMXRT1011_WRITE_ADDR = 0x60000400
UF2_MIMXRT1021_WRITE_ADDR = 0x60000400
UF2_MIMXRT1062_WRITE_ADDR = 0x60000000
