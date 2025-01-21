UF2_FAMILY_ID = 0x4e8f1c5d
CROSS_COMPILE = arm-none-eabi-

ST_HAL_DRIVER = lib/mcu/st/stm32h5xx_hal_driver
ST_CMSIS = lib/mcu/st/cmsis_device_h5
CMSIS_5 = lib/CMSIS_5

# Port Compiler Flags
CFLAGS += \
  -flto \
  -mthumb \
  -mabi=aapcs \
  -mcpu=cortex-m33 \
  -mfloat-abi=hard \
  -mfpu=fpv4-sp-d16 \
  -nostdlib -nostartfiles \
  -DCFG_TUSB_MCU=OPT_MCU_STM32H5

# suppress warning caused by vendor mcu driver
CFLAGS += -Wno-error=cast-align -Wno-error=unused-parameter

ifndef __CC_ARM
  CFLAGS += -D__ARMCC_VERSION=0
endif

# default linker file
ifdef BUILD_APPLICATION
  LD_FILES ?= $(PORT_DIR)/linker/stm32h5_app.ld
else
  LD_FILES ?= $(PORT_DIR)/linker/stm32h5_boot.ld
endif

ifeq (DEBUG,1)
LD_FLASH_BOOT_SIZE := 64K
endif

LDFLAGS += \
	-Wl,--defsym=__flash_boot_size=${LD_FLASH_BOOT_SIZE} \
  -Wl,--defsym=__ram_size=${LD_RAM_SIZE} \

# Port source
SRC_C += \
	ports/stm32h5/boards.c \
	ports/stm32h5/board_flash.c \
	$(ST_CMSIS)/Source/Templates/system_stm32h5xx.c \
	$(ST_HAL_DRIVER)/Src/stm32h5xx_hal.c \
	$(ST_HAL_DRIVER)/Src/stm32h5xx_hal_cortex.c \
	$(ST_HAL_DRIVER)/Src/stm32h5xx_hal_rcc.c \
	$(ST_HAL_DRIVER)/Src/stm32h5xx_hal_rcc_ex.c \
	$(ST_HAL_DRIVER)/Src/stm32h5xx_hal_gpio.c \
	${ST_HAL_DRIVER}/Src/stm32h5xx_hal_pwr.c \
	${ST_HAL_DRIVER}/Src/stm32h5xx_hal_pwr_ex.c \
	$(ST_HAL_DRIVER)/Src/stm32h5xx_hal_flash.c \
	$(ST_HAL_DRIVER)/Src/stm32h5xx_hal_flash_ex.c \
	$(ST_HAL_DRIVER)/Src/stm32h5xx_hal_uart.c

ifndef BUILD_NO_TINYUSB
  SRC_C += lib/tinyusb/src/portable/st/stm32_fsdev/dcd_stm32_fsdev.c
  SRC_C += lib/tinyusb/src/portable/synopsys/dwc2/dwc2_common.c
endif

# Port include
INC += \
	$(TOP)/$(CMSIS_5)/CMSIS/Core/Include \
	$(TOP)/$(ST_CMSIS)/Include \
	$(TOP)/$(ST_HAL_DRIVER)/Inc
