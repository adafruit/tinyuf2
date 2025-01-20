UF2_FAMILY_ID = 0x57755a57
CROSS_COMPILE = arm-none-eabi-

ST_HAL_DRIVER = lib/mcu/st/stm32f4xx_hal_driver
ST_CMSIS = lib/mcu/st/cmsis_device_f4
CMSIS_5 = lib/CMSIS_5

# Port Compiler Flags
CFLAGS += \
  -flto \
  -mthumb \
  -mabi=aapcs \
  -mcpu=cortex-m4 \
  -mfloat-abi=hard \
  -mfpu=fpv4-sp-d16 \
  -nostdlib -nostartfiles \
  -DCFG_TUSB_MCU=OPT_MCU_STM32F4

# suppress warning caused by vendor mcu driver
CFLAGS += -Wno-error=cast-align -Wno-error=unused-parameter

# default linker file
ifdef BUILD_APPLICATION
  LD_FILES ?= $(PORT_DIR)/linker/stm32f4_app.ld
else
  LD_FILES ?= $(PORT_DIR)/linker/stm32f4_boot.ld
endif

# Port source
SRC_C += \
	ports/stm32f4/boards.c \
	ports/stm32f4/board_flash.c \
	$(ST_CMSIS)/Source/Templates/system_stm32f4xx.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal_cortex.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal_rcc.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal_gpio.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal_flash.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal_flash_ex.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal_uart.c

ifndef BUILD_NO_TINYUSB
SRC_C += lib/tinyusb/src/portable/synopsys/dwc2/dcd_dwc2.c
SRC_C += lib/tinyusb/src/portable/synopsys/dwc2/dwc2_common.c
endif

# Port include
INC += \
	$(TOP)/$(CMSIS_5)/CMSIS/Core/Include \
	$(TOP)/$(ST_CMSIS)/Include \
	$(TOP)/$(ST_HAL_DRIVER)/Inc
