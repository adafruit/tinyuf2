UF2_FAMILY_ID = 0x4fb2d5bd
CROSS_COMPILE = arm-none-eabi-

# List of git submodules that is included as part of the UF2 version
GIT_SUBMODULES = nxp tinyusb

# For flash-pyocd-bin target
FLASH_BIN_ADDR = $(UF2_$(MCU)_WRITE_ADDR)

include ../make.mk

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

#---------------------------------------------------------
# Load to SRAM using sdphost
# Note: you may need to give the sdphost binary executable permission first.
#---------------------------------------------------------
SDP_MIMXRT1011_PID = 0x0145
SDP_MIMXRT1011_WRITE_ADDR = 0x20206400
SDP_MIMXRT1011_JUMP_ADDR  = 0x20207000
UF2_MIMXRT1011_WRITE_ADDR = 0x60000400

SDP_MIMXRT1021_PID = 0x0130
SDP_MIMXRT1021_WRITE_ADDR = 0x0400
SDP_MIMXRT1021_JUMP_ADDR  = 0x1000
UF2_MIMXRT1021_WRITE_ADDR = 0x60000400

SDP_MIMXRT1062_PID = 0x0135
SDP_MIMXRT1062_WRITE_ADDR = 0x20208000
SDP_MIMXRT1062_JUMP_ADDR  = 0x20209000
UF2_MIMXRT1062_WRITE_ADDR = 0x60000000

ifeq ($(OS),Windows_NT)
	SDPHOST = sdphost/win/sdphost.exe
else
	UNAME_S := $(shell uname -s)
	UNAME_M := $(shell uname -m)

	ifeq ($(UNAME_S),Darwin)
		SDPHOST = sdphost/mac/sdphost
	endif

	ifeq ($(UNAME_S),Linux)
		ifeq ($(UNAME_M),x86_64)
			SDPHOST = sdphost/linux/amd64/sdphost
		endif
		ifeq ($(UNAME_M),i386)
			SDPHOST = sdphost/linux/i386/sdphost
		endif
	endif
endif

flash-sdp: $(BUILD)/$(OUTNAME).bin
	@if [ -z "$(SDPHOST)" ]; then echo SDPHOST is not found for this machine; exit 1; fi
	$(SDPHOST) -u 0x1fc9,$(SDP_$(MCU)_PID) -- write-file $(SDP_$(MCU)_WRITE_ADDR) $<
	$(SDPHOST) -u 0x1fc9,$(SDP_$(MCU)_PID) -- jump-address $(SDP_$(MCU)_JUMP_ADDR)

#-------------- Self-update  --------------
# RT10xx run entire bootloader from SRAM and
# can directly flash the bootloader region
# without using self-update app as other port
#--------------------------------------------
include ../self_update.mk

# self-update uf2 file
$(SELF_BUILD_OBJ)/$(SELF_OUTNAME).uf2: $(BUILD)/$(OUTNAME).bin $(SELF_OBJ_DIRS)
	@echo CREATE $@
	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py -f $(UF2_FAMILY_ID) -b $(UF2_$(MCU)_WRITE_ADDR) -c -o $@ $<
