UF2_FAMILY_ID = 0x4fb2d5bd
CROSS_COMPILE = arm-none-eabi-

# List of git submodules that is included as part of the UF2 version
GIT_SUBMODULES = nxp tinyusb

include ../make.mk

MCU_DIR = lib/nxp/sdk/devices/$(MCU)
LD_FILES ?= $(PORT_DIR)/linker/$(MCU)_nor.ld $(PORT_DIR)/linker/memory.ld $(PORT_DIR)/linker/common.ld

# Port Compiler Flags
CFLAGS += \
  -mthumb \
  -mabi=aapcs \
  -mcpu=cortex-m7 \
  -mfloat-abi=hard \
  -mfpu=fpv5-d16 \
  -D__ARMVFP__=0 -D__ARMFPV5__=0 \
  -DCFG_TUSB_MCU=OPT_MCU_MIMXRT10XX

# mcu driver cause following warnings
CFLAGS += -Wno-error=unused-parameter

# Port source
PORT_SRC_C = \
	$(addprefix $(CURRENT_PATH)/, $(wildcard *.c)) \
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

SRC_C += \
	$(PORT_SRC_C) \
	lib/tinyusb/src/portable/nxp/transdimension/dcd_transdimension.c

SRC_S += $(MCU_DIR)/gcc/startup_$(MCU).S

# Port include
INC += \
	$(TOP)/$(MCU_DIR)/../../CMSIS/Include \
	$(TOP)/$(MCU_DIR) \
	$(TOP)/$(MCU_DIR)/drivers \
	$(TOP)/$(MCU_DIR)/xip \
	$(TOP)/$(MCU_DIR)/project_template

include ../rules.mk

# Flash binary to correct bootloader address
flash-pyocd-imxrt: $(BUILD)/$(OUTNAME).bin
	pyocd flash -t $(PYOCD_TARGET) -a 0x60000400 $<
	pyocd reset -t $(PYOCD_TARGET)

#-------------- Self-update  --------------
# RT10xx run entire bootloader from SRAM and
# can directly flash the bootloader region
# without using self-update app as other port
#--------------------------------------------
include ../self_update.mk

# self-update uf2 file
$(SELF_BUILD_OBJ)/$(SELF_OUTNAME).uf2: $(BUILD)/$(OUTNAME).bin $(SELF_OBJ_DIRS)
	@echo CREATE $@
	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py -f $(UF2_FAMILY_ID) -b 0x60000400 -c -o $@ $<
