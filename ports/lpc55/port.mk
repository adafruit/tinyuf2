UF2_FAMILY_ID = 0x2abc77ec
CROSS_COMPILE = arm-none-eabi-

SDK_DIR = lib/mcu/nxp/mcux-sdk
MCU_DIR = $(SDK_DIR)/devices/$(MCU)
CMSIS_5 = lib/CMSIS_5

# Port Compiler Flags
CFLAGS += \
  -flto \
  -mthumb \
  -mabi=aapcs \
  -mcpu=cortex-m33 \
  -mfloat-abi=hard \
  -mfpu=fpv5-sp-d16 \
  -DCFG_TUSB_MCU=OPT_MCU_LPC55XX

# suppress warning caused by vendor mcu driver
CFLAGS += -Wno-error=unused-parameter -Wno-error=float-equal

SRC_S += $(MCU_DIR)/gcc/startup_$(MCU_CORE).S

LIBS += $(TOP)/$(MCU_DIR)/gcc/libpower_hardabi.a

# Port source
SRC_C += \
	$(MCU_DIR)/system_$(MCU_CORE).c \
	$(MCU_DIR)/project_template/clock_config.c \
	$(MCU_DIR)/drivers/fsl_clock.c \
	$(MCU_DIR)/drivers/fsl_power.c \
	$(MCU_DIR)/drivers/fsl_reset.c \
	$(SDK_DIR)/drivers/flexcomm/fsl_flexcomm.c \
	$(SDK_DIR)/drivers/flexcomm/fsl_usart.c \
	$(SDK_DIR)/drivers/iap1/fsl_iap.c \
	$(SDK_DIR)/drivers/lpc_gpio/fsl_gpio.c \
	$(SDK_DIR)/drivers/lpc_rtc/fsl_rtc.c \

# Port include
INC += \
	$(TOP)/$(PORT_DIR) \
	$(TOP)/$(BOARD_DIR) \
	$(TOP)/$(CMSIS_5)/CMSIS/Core/Include \
	$(TOP)/$(MCU_DIR) \
	$(TOP)/$(MCU_DIR)/project_template \
	$(TOP)/$(MCU_DIR)/drivers \
	$(TOP)/$(SDK_DIR)/drivers/common \
	$(TOP)/$(SDK_DIR)/drivers/flexcomm \
	$(TOP)/$(SDK_DIR)/drivers/iap1 \
	$(TOP)/$(SDK_DIR)/drivers/lpc_gpio \
	$(TOP)/$(SDK_DIR)/drivers/lpc_iocon \
	$(TOP)/$(SDK_DIR)/drivers/lpc_rtc \
	$(TOP)/$(SDK_DIR)/drivers/sctimer
