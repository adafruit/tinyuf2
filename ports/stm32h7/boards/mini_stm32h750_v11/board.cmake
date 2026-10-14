set(MCU h750xx)
set(SPI_FLASH W25Qx_SPI)
set(QSPI_FLASH W25Qx_QSPI)
set(DISPLAY_DRV ST7735)
set(JLINK_DEVICE stm32h750vb)

function(update_board TARGET)
  target_sources(${TARGET} PUBLIC
    ${ST_CMSIS}/Source/Templates/gcc/startup_stm32h750xx.s
    )
  target_compile_definitions(${TARGET} PUBLIC
    STM32H750xx
    HSE_VALUE=25000000U
    TINYUF2_DISPLAY=1
    TINYUF2_LED=1
    BOARD_QSPI_FLASH_EN=1
    BOARD_SPI_FLASH_EN=1
    BOARD_AXISRAM_EN=1
    BOARD_FLASH_APP_START=0x90000000
    TRAP_EXC
    )
endfunction()
