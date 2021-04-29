UF2_FAMILY_ID = 0x2abc77ec
CROSS_COMPILE = arm-none-eabi-

# List of git submodules that is included as part of the UF2 version
GIT_SUBMODULES = nxp/mcux-sdk sct_neopixel tinyusb

include ../make.mk

SDK_DIR = lib/nxp/mcux-sdk
MCU_DIR = $(SDK_DIR)/devices/$(MCU)
LD_FILES ?= $(MCU_DIR)/gcc/$(MCU_CORE)_flash.ld

# Port Compiler Flags
CFLAGS += \
  -flto \
  -mthumb \
  -mabi=aapcs \
  -mcpu=cortex-m33 \
  -mfloat-abi=hard \
  -mfpu=fpv5-sp-d16 \
  -DCFG_TUSB_MCU=OPT_MCU_LPC55XX

# suppress warning caused by vendor mcu driver
CFLAGS += -Wno-error=unused-parameter -Wno-error=float-equal

# Port source
PORT_SRC_C += \
	$(addprefix $(CURRENT_PATH)/, $(wildcard *.c)) \
	$(MCU_DIR)/system_$(MCU_CORE).c \
	$(MCU_DIR)/project_template/clock_config.c \
	$(MCU_DIR)/drivers/fsl_clock.c \
	$(MCU_DIR)/drivers/fsl_power.c \
	$(MCU_DIR)/drivers/fsl_reset.c \
	$(SDK_DIR)/drivers/flexcomm/fsl_flexcomm.c \
	$(SDK_DIR)/drivers/flexcomm/fsl_usart.c \
	$(SDK_DIR)/drivers/iap1/fsl_iap.c \
	$(SDK_DIR)/drivers/lpc_gpio/fsl_gpio.c \
	$(SDK_DIR)/drivers/lpc_rtc/fsl_rtc.c \

SRC_C += \
	$(PORT_SRC_C) \
	lib/tinyusb/src/portable/nxp/lpc_ip3511/dcd_lpc_ip3511.c \

SRC_S += $(MCU_DIR)/gcc/startup_$(MCU_CORE).S

LIBS += $(TOP)/$(MCU_DIR)/gcc/libpower_hardabi.a

# Port include
INC += \
	$(TOP)/$(SDK_DIR)/CMSIS/Include \
	$(TOP)/$(MCU_DIR) \
	$(TOP)/$(MCU_DIR)/project_template \
	$(TOP)/$(MCU_DIR)/drivers \
	$(TOP)/$(SDK_DIR)/drivers/common \
	$(TOP)/$(SDK_DIR)/drivers/flexcomm \
	$(TOP)/$(SDK_DIR)/drivers/iap1 \
	$(TOP)/$(SDK_DIR)/drivers/lpc_gpio \
	$(TOP)/$(SDK_DIR)/drivers/lpc_iocon \
	$(TOP)/$(SDK_DIR)/drivers/lpc_rtc \

include ../rules.mk

#-------------- Self-update  --------------
SELF_CFLAGS  = $(CFLAGS) -DTINYUF2_SELF_UPDATE
SELF_LDFLAGS = $(LDFLAGS)
SELF_LD_FILES ?= $(LD_FILES)
SELF_ASFLAGS = $(ASFLAGS)

include ../self_update.mk

# self-update uf2 file
$(SELF_BUILD_OBJ)/$(SELF_OUTNAME).uf2: $(SELF_BUILD_OBJ)/$(SELF_OUTNAME).hex
	@echo CREATE $@
	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py -f $(UF2_FAMILY_ID) -c -o $@ $^

$(SELF_BUILD_OBJ)/$(SELF_OUTNAME).hex: $(SELF_BUILD_OBJ)/$(SELF_OUTNAME).elf
	@echo CREATE $@
	@$(OBJCOPY) -O ihex $^ $@

# required for self-update elf compile
$(SELF_BUILD_OBJ)/self_update/$(OUTNAME).c:
	@echo "const unsigned long bindata_len = 1;" > $@
	@echo "const unsigned char bindata[] __attribute__((aligned(16))) = { 0 };" >> $@
	#$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py --carray $^ -o $@
