UF2_FAMILY_ID = 0x699b62ec

# Toolchain from https://github.com/xpack-dev-tools/riscv-none-elf-gcc-xpack
CROSS_COMPILE ?= riscv-none-elf-

CH32_FAMILY = ch32v20x
SDK_DIR = lib/mcu/wch/ch32v20x
SDK_SRC_DIR = $(SDK_DIR)/EVT/EXAM/SRC

CPU_CORE ?= rv32imac-ilp32

CFLAGS += \
	-march=rv32imac_zicsr \
	-mabi=ilp32 \

# Port0 use FSDev, Port1 use USBFS
USBPORT ?= 0

# Port Compiler Flags
CFLAGS += \
	-mcmodel=medany \
	-ffat-lto-objects \
	-flto \
	-DCH32V20x_${MCU_VARIANT} \
	-DCFG_TUSB_MCU=OPT_MCU_CH32V20X

ifeq ($(USBPORT),0)
  $(info "Using FSDEV driver")
  CFLAGS += -DCFG_TUD_WCH_USBIP_FSDEV=1
else
  $(info "Using USBFS driver")
  CFLAGS += -DCFG_TUD_WCH_USBIP_USBFS=1
endif

LDFLAGS += \
	-nostdlib -nostartfiles \
	#--specs=nosys.specs --specs=nano.specs \

# default linker file
ifdef BUILD_APPLICATION
  LD_FILES ?= $(PORT_DIR)/linker/${CH32_FAMILY}.ld
else
  LD_FILES ?= $(PORT_DIR)/linker/${CH32_FAMILY}_boot.ld
endif

# Port source
SRC_C += \
	$(PORT_DIR)/boards.c \
	$(PORT_DIR)/system_ch32v20x.c \
	$(SDK_SRC_DIR)/Core/core_riscv.c \
	$(SDK_SRC_DIR)/Peripheral/src/ch32v20x_flash.c \
	$(SDK_SRC_DIR)/Peripheral/src/ch32v20x_gpio.c \
	$(SDK_SRC_DIR)/Peripheral/src/ch32v20x_misc.c \
	$(SDK_SRC_DIR)/Peripheral/src/ch32v20x_rcc.c \
	$(SDK_SRC_DIR)/Peripheral/src/ch32v20x_usart.c \

ifndef BUILD_NO_TINYUSB
SRC_C += \
  lib/tinyusb/src/portable/st/stm32_fsdev/dcd_stm32_fsdev.c \
	lib/tinyusb/src/portable/wch/dcd_ch32_usbfs.c
endif

SRC_S += $(SDK_SRC_DIR)/Startup/startup_ch32v20x_${MCU_VARIANT}.S

# Port include
INC += \
	$(TOP)/$(BOARD_DIR) \
	$(TOP)/$(SDK_SRC_DIR)/Peripheral/inc \

OPENOCD_WCH_OPTION=-f $(TOP)/$(PORT_DIR)/wch-riscv.cfg
flash: flash-openocd-wch
