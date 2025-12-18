set(LD_FLASH_BOOT_SIZE 24K)
set(LD_RAM_SIZE 32K)
set(JLINK_DEVICE stm32h503cb)

function(update_board TARGET)
  target_sources(${TARGET} PUBLIC
    ${ST_CMSIS}/Source/Templates/gcc/startup_stm32h503xx.s
    )
  target_compile_definitions(${TARGET} PUBLIC
    STM32H503xx
    HSE_VALUE=8000000
    )
endfunction()
