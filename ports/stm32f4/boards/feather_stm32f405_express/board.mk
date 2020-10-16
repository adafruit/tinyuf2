CFLAGS += \
  -flto \
  -mthumb \
  -mabi=aapcs \
  -mcpu=cortex-m4 \
  -mfloat-abi=hard \
  -mfpu=fpv4-sp-d16 \
  -nostdlib -nostartfiles \
  -DSTM32F405xx \
  -DCFG_TUSB_MCU=OPT_MCU_STM32F4

# suppress warning caused by vendor mcu driver
CFLAGS += -Wno-error=cast-align

ST_HAL_DRIVER = lib/st/stm32f4xx_hal_driver
ST_CMSIS = lib/st/cmsis_device_f4
CMSIS_5 = lib/CMSIS_5

# All source paths should be relative to the top level.
LD_FILE = ports/$(PORT)/boards/$(BOARD)/STM32F405RGTx_FLASH.ld

SRC_C += \
	$(ST_CMSIS)/Source/Templates/system_stm32f4xx.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal_cortex.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal_rcc.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal_gpio.c \
	$(ST_HAL_DRIVER)/Src/stm32f4xx_hal_uart.c

SRC_S += \
	$(ST_CMSIS)/Source/Templates/gcc/startup_stm32f405xx.s

INC += \
	$(TOP)/$(CMSIS_5)/CMSIS/Core/Include \
	$(TOP)/$(ST_CMSIS)/Include \
	$(TOP)/$(ST_HAL_DRIVER)/Inc

TINYUSB_DCD = st/synopsys/dcd_synopsys.c

# For flash-jlink target
JLINK_DEVICE = stm32f405rg

flash: flash-jlink

# flash target ROM bootloader
#flash: $(BUILD)/$(BOARD)-firmware.bin
#	dfu-util -R -a 0 --dfuse-address 0x08000000 -D $<
