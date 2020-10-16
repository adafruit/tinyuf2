CFLAGS += \
  -DSTM32F405xx \
  -DHSE_VALUE=12000000U

# All source paths should be relative to the top level.
LD_FILE = ports/$(PORT)/boards/$(BOARD)/STM32F405RGTx_FLASH.ld

SRC_S += \
	$(ST_CMSIS)/Source/Templates/gcc/startup_stm32f405xx.s

# For flash-jlink target
JLINK_DEVICE = stm32f405rg

flash: flash-jlink
