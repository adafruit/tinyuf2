UF2_FAMILY_ID = 0x5ee21072
CROSS_COMPILE = arm-none-eabi-

ST_HAL_DRIVER = lib/mcu/st/stm32f1xx_hal_driver
ST_CMSIS = lib/mcu/st/cmsis_device_f1
CMSIS_5 = lib/CMSIS_5

# Port Compiler Flags
CFLAGS += \
  -flto \
  -mthumb \
  -mabi=aapcs \
  -mcpu=cortex-m3 \
  -mfloat-abi=soft \
  -nostdlib -nostartfiles \
  -DCFG_TUSB_MCU=OPT_MCU_STM32F1

# suppress warning caused by vendor mcu driver
CFLAGS += -Wno-error=cast-align -Wno-error=unused-parameter

# default linker file
ifdef BUILD_APPLICATION
  LD_FILES ?= $(PORT_DIR)/linker/stm32f1_app.ld
else
  LD_FILES ?= $(PORT_DIR)/linker/stm32f1_boot.ld
endif

# Port source
SRC_C += \
	ports/stm32f1/boards.c \
	ports/stm32f1/board_flash.c \
	$(ST_CMSIS)/Source/Templates/system_stm32f1xx.c \
	$(ST_HAL_DRIVER)/Src/stm32f1xx_hal.c \
	$(ST_HAL_DRIVER)/Src/stm32f1xx_hal_cortex.c \
	$(ST_HAL_DRIVER)/Src/stm32f1xx_hal_rcc.c \
	$(ST_HAL_DRIVER)/Src/stm32f1xx_hal_rcc_ex.c \
	$(ST_HAL_DRIVER)/Src/stm32f1xx_hal_gpio.c \
	$(ST_HAL_DRIVER)/Src/stm32f1xx_hal_dma.c \
	$(ST_HAL_DRIVER)/Src/stm32f1xx_hal_flash.c \
	$(ST_HAL_DRIVER)/Src/stm32f1xx_hal_flash_ex.c \
	$(ST_HAL_DRIVER)/Src/stm32f1xx_hal_uart.c

ifndef BUILD_NO_TINYUSB
SRC_C += lib/tinyusb/src/portable/st/stm32_fsdev/dcd_stm32_fsdev.c
SRC_C += lib/tinyusb/src/portable/st/stm32_fsdev/fsdev_common.c
endif

# Port include
INC += \
	$(TOP)/$(CMSIS_5)/CMSIS/Core/Include \
	$(TOP)/$(ST_CMSIS)/Include \
	$(TOP)/$(ST_HAL_DRIVER)/Inc
