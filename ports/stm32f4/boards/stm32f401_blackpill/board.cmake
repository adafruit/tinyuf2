set(JLINK_DEVICE stm32f411ce)

function(update_board TARGET)
  target_sources(${TARGET} PUBLIC
    ${ST_CMSIS}/Source/Templates/gcc/startup_stm32f411xe.s
    )
  target_compile_definitions(${TARGET} PUBLIC
    STM32F411xE
    HSE_VALUE=25000000U
    )
endfunction()
