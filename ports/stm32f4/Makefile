PORT = stm32f4

#-------------- Cross Compiler  ------------
CROSS_COMPILE = arm-none-eabi-

CC = $(CROSS_COMPILE)gcc
CXX = $(CROSS_COMPILE)g++
OBJCOPY = $(CROSS_COMPILE)objcopy
SIZE = $(CROSS_COMPILE)size
MKDIR = mkdir
SED = sed
CP = cp
RM = rm

ST_HAL_DRIVER = lib/st/stm32f4xx_hal_driver
ST_CMSIS = lib/st/cmsis_device_f4
CMSIS_5 = lib/CMSIS_5

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

# suppress warning caused by vendor mcu driver
CFLAGS += -Wno-error=cast-align

# Port source
SRC_C += \
	$(addprefix $(CURRENT_PATH)/, $(wildcard *.c)) \
	lib/tinyusb/src/portable/st/synopsys/dcd_synopsys.c \
	$(ST_CMSIS)/Source/Templates/system_stm32f4xx.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal_cortex.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal_rcc.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal_gpio.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal_uart.c

# Port include
INC += \
	$(TOP)/$(CMSIS_5)/CMSIS/Core/Include \
	$(TOP)/$(ST_CMSIS)/Include \
	$(TOP)/$(ST_HAL_DRIVER)/Inc

include ../rules.mk

# flash target ROM bootloader
flash-dfu-util: $(BUILD)/$(BOARD)-firmware.bin
	dfu-util -R -a 0 --dfuse-address 0x08000000 -D $<
