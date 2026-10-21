JLINK_DEVICE = stm32h743zi
# apps run from internal flash, see apps/app.mk
BOARD_PFLASH_APP_EN = 1

CFLAGS += \
  -DSTM32H743xx \
  -DHSE_VALUE=8000000U \
  -DTINYUF2_LED=1 \
  -DBOARD_PFLASH_APP_EN=1 \
  -DBOARD_FLASH_APP_START=0x08020000 \
  -DTRAP_EXC

MCU = h743xx

SRC_S += \
  $(ST_CMSIS)/Source/Templates/gcc/startup_stm32h743xx.s
