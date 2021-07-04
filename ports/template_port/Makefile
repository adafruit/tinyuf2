UF2_FAMILY_ID = 0x00000000
CROSS_COMPILE = arm-none-eabi-

# List of git submodules that is included as part of the UF2 version
GIT_SUBMODULES = tinyusb

include ../make.mk

# Port Compiler Flags
CFLAGS += \
  -flto \
  -mthumb \
  -mabi=aapcs \
  -mcpu=cortex-m3 \
  -DCFG_TUSB_MCU=OPT_MCU_NONE

# suppress warning caused by vendor mcu driver
CFLAGS += -Wno-error=cast-align -Wno-error=unused-parameter

LD_FILES ?=

# Port source
PORT_SRC_C += \
	$(addprefix $(CURRENT_PATH)/, $(wildcard *.c))

SRC_C += \
	$(PORT_SRC_C) \
	lib/tinyusb/src/portable/template/dcd_template.c \

SRC_S +=

# Port include
INC +=

include ../rules.mk

#-------------- Self-update  --------------
self-update:
	@echo "not implemented yet"
