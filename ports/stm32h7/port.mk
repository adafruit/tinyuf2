include $(TOP)/$(PORT_DIR)/boards/$(BOARD)/board.mk

UF2_FAMILY_ID = 0x6db66082
CROSS_COMPILE = arm-none-eabi-

ST_HAL_DRIVER = lib/mcu/st/stm32h7xx_hal_driver
ST_CMSIS = lib/mcu/st/cmsis_device_h7
CMSIS_5 = lib/CMSIS_5

# Compiler flags
CFLAGS += \
  -mthumb \
  -mabi=aapcs \
  -mcpu=cortex-m7 \
  -mfloat-abi=hard \
  -mfpu=fpv5-d16 \
  -DCFG_TUSB_MCU=OPT_MCU_STM32H7

ifeq ($(LTO_ON),1)
CFLAGS += -flto
endif

# suppress warning caused by vendor mcu driver
CFLAGS += -Wno-error=cast-align -Wno-error=unused-parameter -Wno-error=unused-but-set-variable -Wno-error=unused-function

ifeq ($(SPI_FLASH),W25Qx_SPI)
INC += \
  $(CURRENT_PATH)/components/w25qxx/ \

SRC_C += \
	$(TOP)/$(PORT_DIR)/components/w25qxx/w25qxx.c
endif

ifeq ($(QSPI_FLASH),W25Qx_QSPI)
INC += \
  $(CURRENT_PATH)/components/w25qxx/ \

SRC_C += \
	$(TOP)/$(PORT_DIR)/components/w25qxx/w25qxx_qspi.c
endif

ifeq ($(DISPLAY_DRV),ST7735)
INC += \
  $(CURRENT_PATH)/components/w25qxx/ \

SRC_C += \
	$(TOP)/$(PORT_DIR)/components/st7735/st7735.c
endif

# Source
SRC_C += \
  $(ST_CMSIS)/Source/Templates/system_stm32h7xx.c \
  $(ST_HAL_DRIVER)/Src/stm32h7xx_hal.c \
  $(ST_HAL_DRIVER)/Src/stm32h7xx_hal_cortex.c \
  $(ST_HAL_DRIVER)/Src/stm32h7xx_hal_rcc.c \
  $(ST_HAL_DRIVER)/Src/stm32h7xx_hal_rcc_ex.c \
  $(ST_HAL_DRIVER)/Src/stm32h7xx_hal_gpio.c \
  $(ST_HAL_DRIVER)/Src/stm32h7xx_hal_flash.c \
  $(ST_HAL_DRIVER)/Src/stm32h7xx_hal_flash_ex.c \
  $(ST_HAL_DRIVER)/Src/stm32h7xx_hal_uart.c \
  $(ST_HAL_DRIVER)/Src/stm32h7xx_hal_spi.c \
  $(ST_HAL_DRIVER)/Src/stm32h7xx_hal_pwr.c \
  $(ST_HAL_DRIVER)/Src/stm32h7xx_hal_qspi.c \
  $(ST_HAL_DRIVER)/Src/stm32h7xx_hal_mdma.c \
  $(ST_HAL_DRIVER)/Src/stm32h7xx_hal_pwr_ex.c \
  $(TOP)/$(PORT_DIR)/components/st7735/fonts.c \


ifndef BUILD_NO_TINYUSB
SRC_C += lib/tinyusb/src/portable/synopsys/dwc2/dcd_dwc2.c
SRC_C += lib/tinyusb/src/portable/synopsys/dwc2/dwc2_common.c
endif

# Includes
INC += \
  $(TOP)/$(BOARD_PATH) \
  $(TOP)/$(CMSIS_5)/CMSIS/Core/Include \
  $(CURRENT_PATH)/components/st7735/ \
  $(CURRENT_PATH)/components/w25qxx/ \
  $(TOP)/$(PORT_DIR)/ \
  $(TOP)/$(BOARD_DIR) \
  $(TOP)/$(ST_CMSIS)/Include \
  $(TOP)/$(ST_HAL_DRIVER)/Inc
