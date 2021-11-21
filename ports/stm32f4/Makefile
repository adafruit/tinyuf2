UF2_FAMILY_ID = 0x57755a57
CROSS_COMPILE = arm-none-eabi-

ST_HAL_DRIVER = lib/st/stm32f4xx_hal_driver
ST_CMSIS = lib/st/cmsis_device_f4
CMSIS_5 = lib/CMSIS_5

# List of git submodules that is included as part of the UF2 version
GIT_SUBMODULES = st/cmsis_device_f4 st/stm32f4xx_hal_driver tinyusb

include ../make.mk

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

# Allow to override application start vector
ifneq ($(APP_START),)
  CFLAGS += -DBOARD_FLASH_APP_START=$(APP_START)
endif

# suppress warning caused by vendor mcu driver
CFLAGS += -Wno-error=cast-align -Wno-error=unused-parameter

LD_FILES ?= $(PORT_DIR)/linker/stm32f4.ld

# Port source
PORT_SRC_C += \
	$(addprefix $(CURRENT_PATH)/, $(wildcard *.c)) \
	$(ST_CMSIS)/Source/Templates/system_stm32f4xx.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal_cortex.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal_rcc.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal_gpio.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal_flash.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal_flash_ex.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal_uart.c

SRC_C += \
	$(PORT_SRC_C) \
	lib/tinyusb/src/portable/st/synopsys/dcd_synopsys.c \
	
# Port include
INC += \
	$(TOP)/$(CMSIS_5)/CMSIS/Core/Include \
	$(TOP)/$(ST_CMSIS)/Include \
	$(TOP)/$(ST_HAL_DRIVER)/Inc

include ../rules.mk

# flash target ROM bootloader
flash-dfu-util: $(BUILD)/$(OUTNAME).bin
	dfu-util -R -a 0 --dfuse-address 0x08000000 -D $<

#-------------- Self-update  --------------
self-update:
	@echo "not implemented yet"
