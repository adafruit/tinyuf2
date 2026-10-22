set(MCU h743xx)
set(JLINK_DEVICE stm32h743zi)
# apps run from internal flash, see app.cmake
set(BOARD_PFLASH_APP_EN 1)

function(update_board TARGET)
  target_sources(${TARGET} PUBLIC
    ${ST_CMSIS}/Source/Templates/gcc/startup_stm32h743xx.s
    )
  target_compile_definitions(${TARGET} PUBLIC
    STM32H743xx
    HSE_VALUE=8000000U
    TINYUF2_LED=1
    BOARD_PFLASH_APP_EN=1
    BOARD_FLASH_APP_START=0x08020000
    TRAP_EXC
    )
endfunction()
