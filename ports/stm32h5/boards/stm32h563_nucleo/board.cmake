set(LD_FLASH_BOOT_SIZE 32K)
set(LD_RAM_SIZE 640K)
set(JLINK_DEVICE stm32h563zi)

function(update_board TARGET)
  target_sources(${TARGET} PUBLIC
    ${ST_CMSIS}/Source/Templates/gcc/startup_stm32h563xx.s
    )
  target_compile_definitions(${TARGET} PUBLIC
    STM32H563xx
    HSE_VALUE=8000000
    )
endfunction()
