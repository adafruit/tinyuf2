UF2_FAMILY_ID = 0x2abc77ec
CROSS_COMPILE = arm-none-eabi-

include ../make.mk

MCU_DIR = lib/nxp/sdk/devices/$(MCU)
LD_FILES ?= $(MCU_DIR)/gcc/$(MCU)_cm33_core0_flash.ld

# Version
GIT_VERSION := $(shell git describe --dirty --always --tags)
GIT_SUBMODULE_VERSIONS := $(shell git submodule status $(addprefix ../../lib/, tinyusb) | cut -d" " -f3,4 | paste -s -d" " -)
GIT_SUBMODULE_VERSIONS := $(subst ../../lib/,,$(GIT_SUBMODULE_VERSIONS))

# Port Compiler Flags
CFLAGS += \
  -flto \
  -mthumb \
  -mabi=aapcs \
  -mcpu=cortex-m33 \
  -mfloat-abi=hard \
  -mfpu=fpv5-sp-d16 \
  -DCFG_TUSB_MCU=OPT_MCU_LPC55XX \
  -DBOARD_UF2_FAMILY_ID=$(UF2_FAMILY_ID) \
  -DUF2_VERSION='"$(GIT_VERSION) - $(GIT_SUBMODULE_VERSIONS)"'

# suppress warning caused by vendor mcu driver
CFLAGS += -Wno-error=unused-parameter -Wno-error=float-equal


# Port source
PORT_SRC_C += \
	$(addprefix $(CURRENT_PATH)/, $(wildcard *.c)) \
	$(MCU_DIR)/system_$(MCU)_cm33_core0.c \
	$(MCU_DIR)/drivers/fsl_clock.c \
	$(MCU_DIR)/drivers/fsl_gpio.c \
	$(MCU_DIR)/drivers/fsl_power.c \
	$(MCU_DIR)/drivers/fsl_reset.c	

SRC_C += \
	$(PORT_SRC_C) \
	lib/tinyusb/src/portable/nxp/lpc_ip3511/dcd_lpc_ip3511.c \

SRC_S += $(MCU_DIR)/gcc/startup_$(MCU)_cm33_core0.S

LIBS += $(TOP)/$(MCU_DIR)/gcc/libpower_hardabi.a

# Port include
INC += \
	$(TOP)/$(MCU_DIR)/../../CMSIS/Include \
	$(TOP)/$(MCU_DIR) \
	$(TOP)/$(MCU_DIR)/drivers

include ../rules.mk

#-------------- Self-update  --------------
SELF_CFLAGS  = $(CFLAGS) -DTINYUF2_SELF_UPDATE
SELF_LDFLAGS = $(LDFLAGS)
SELF_LD_FILES ?= $(LD_FILES)
SELF_ASFLAGS = $(ASFLAGS)

include ../self_update.mk

# required for uf2 conversion
$(SELF_BUILD_OBJ)/$(SELF_OUTNAME).hex: $(SELF_BUILD_OBJ)/$(SELF_OUTNAME).elf
	@echo CREATE $@
	@$(OBJCOPY) -O ihex $^ $@

# required for self-update elf compile
$(SELF_BUILD_OBJ)/self_update/$(OUTNAME).c:
	@echo "const unsigned long bindata_len = 1;" > $@
	@echo "const unsigned char bindata[] __attribute__((aligned(16))) = { 0 };" >> $@
	#$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py --carray $^ -o $@
