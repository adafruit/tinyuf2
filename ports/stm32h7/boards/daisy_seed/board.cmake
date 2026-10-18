set(MCU h750xx)
set(QSPI_FLASH IS25LP064A)

function(update_board TARGET)
  target_sources(${TARGET} PUBLIC
    ${ST_CMSIS}/Source/Templates/gcc/startup_stm32h750xx.s
    )
  target_compile_definitions(${TARGET} PUBLIC
    STM32H750xx
    HSE_VALUE=16000000U
    TINYUF2_LED=1
    BOARD_QSPI_FLASH_EN=1
    BOARD_AXISRAM_EN=1
    BOARD_FLASH_ADDR_ZERO=0x90000000
    BOARD_FLASH_APP_START=0x90000000
    TRAP_EXC
    )
endfunction()
