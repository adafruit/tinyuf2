UF2_FAMILY_ID = 0x6b846188
CROSS_COMPILE = arm-none-eabi-

ST_HAL_DRIVER = lib/st/stm32f3xx_hal_driver
ST_CMSIS = lib/st/cmsis_device_f3
CMSIS_5 = lib/CMSIS_5

# List of git submodules that is included as part of the UF2 version
GIT_SUBMODULES = CMSIS_5 st tinyusb

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
  -VECT_TAB_OFFSET=$(BOOTLOADER_SIZE)\
  -DCFG_TUSB_MCU=OPT_MCU_STM32F3

LDFLAGS += \
  FLASH_OFFSET=$(BOOTLOADER_SIZE)

# suppress warning caused by vendor mcu driver
CFLAGS += -Wno-error=cast-align -Wno-error=unused-parameter -Wno-uninitialized

LD_FILES ?= $(PORT_DIR)/linker/STM32F303VCTx_FLASH.ld

# Port source
PORT_SRC_C += \
	$(addprefix $(CURRENT_PATH)/, $(wildcard *.c)) \
	$(ST_CMSIS)/Source/Templates/system_stm32f3xx.c \
	$(ST_HAL_DRIVER)/Src/stm32f3xx_hal.c \
	$(ST_HAL_DRIVER)/Src/stm32f3xx_hal_cortex.c \
	$(ST_HAL_DRIVER)/Src/stm32f3xx_hal_rcc.c \
	$(ST_HAL_DRIVER)/Src/stm32f3xx_hal_rcc_ex.c \
	$(ST_HAL_DRIVER)/Src/stm32f3xx_hal_gpio.c \
	$(ST_HAL_DRIVER)/Src/stm32f3xx_hal_flash.c \
	$(ST_HAL_DRIVER)/Src/stm32f3xx_hal_flash_ex.c \
	$(ST_HAL_DRIVER)/Src/stm32f3xx_hal_uart.c

SRC_C += \
	$(PORT_SRC_C) \
	lib/tinyusb/src/portable/st/stm32_fsdev/dcd_stm32_fsdev.c \

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

# self-update uf2 file
$(SELF_BUILD_OBJ)/$(SELF_OUTNAME).uf2: $(SELF_BUILD_OBJ)/$(SELF_OUTNAME).hex
	@echo CREATE $@
	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py -f $(UF2_FAMILY_ID) -c -o $@ $^

$(SELF_BUILD_OBJ)/$(SELF_OUTNAME).hex: $(SELF_BUILD_OBJ)/$(SELF_OUTNAME).elf
	@echo CREATE $@
	@$(OBJCOPY) -O ihex $^ $@

# required for self-update elf compile
$(SELF_BUILD_OBJ)/self_update/$(OUTNAME).c:
	@echo "const unsigned long bindata_len = 1;" > $@
	@echo "const unsigned char bindata[] __attribute__((aligned(16))) = { 0 };" >> $@
	#$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py --carray $^ -o $@
