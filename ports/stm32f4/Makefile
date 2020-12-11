PORT = stm32f4
UF2_FAMILY_ID = 0x57755a57

#-------------- Cross Compiler  ------------
CROSS_COMPILE = arm-none-eabi-

CC = $(CROSS_COMPILE)gcc
OBJCOPY = $(CROSS_COMPILE)objcopy
SIZE = $(CROSS_COMPILE)size

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
  -DCFG_TUSB_MCU=OPT_MCU_STM32F4 \
  -DBOARD_UF2_FAMILY_ID=$(UF2_FAMILY_ID)

# suppress warning caused by vendor mcu driver
CFLAGS += -Wno-error=cast-align -Wno-error=unused-parameter

LD_FILES ?= ports/$(PORT)/linker/stm32f4.ld

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
SELF_CFLAGS  = $(CFLAGS) -DTINYUF2_SELF_UPDATE
SELF_LDFLAGS = $(LDFLAGS)
SELF_LD_FILES ?= $(LD_FILES)
SELF_ASFLAGS = $(ASFLAGS)

include ../self_update.mk

# required for uf2 conversion
$(SELF_BUILD_OBJ)/$(SELF_OUTNAME).hex: $(SELF_BUILD_OBJ)/$(SELF_OUTNAME).elf
	@echo CREATE $@
	@$(OBJCOPY) -O ihex $^ $@

# required for self-update elf compile
$(SELF_BUILD_OBJ)/self_update/$(OUTNAME).c:
	@echo "const unsigned long bindata_len = 1;" > $@
	@echo "const unsigned char bindata[] __attribute__((aligned(16))) = { 0 };" >> $@
	#$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py --carray $^ -o $@
