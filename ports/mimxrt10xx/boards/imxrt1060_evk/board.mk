MCU = MIMXRT1062
CFLAGS += -DCPU_MIMXRT1062DVL6A

# mcu driver cause following warnings
CFLAGS += -Wno-error=unused-parameter

MCU_DIR = lib/nxp/sdk/devices/MIMXRT1062

# All source paths should be relative to the top level.
LD_FILE = $(MCU_DIR)/gcc/MIMXRT1062xxxxx_flexspi_nor.ld

SRC_C += \
	$(MCU_DIR)/system_MIMXRT1062.c \
	$(MCU_DIR)/xip/fsl_flexspi_nor_boot.c \
	$(MCU_DIR)/project_template/clock_config.c \
	$(MCU_DIR)/drivers/fsl_clock.c \
	$(MCU_DIR)/drivers/fsl_gpio.c \
	$(MCU_DIR)/drivers/fsl_common.c \
	$(MCU_DIR)/drivers/fsl_lpuart.c

INC += \
	$(TOP)/$(MCU_DIR)/../../CMSIS/Include \
	$(TOP)/$(MCU_DIR) \
	$(TOP)/$(MCU_DIR)/drivers \
	$(TOP)/$(MCU_DIR)/project_template \

SRC_S += $(MCU_DIR)/gcc/startup_MIMXRT1062.S

# For flash-jlink target
JLINK_DEVICE = MIMXRT1062xxx6A

# For flash-pyocd target
PYOCD_TARGET = mimxrt1060

# flash using pyocd
flash: flash-pyocd
