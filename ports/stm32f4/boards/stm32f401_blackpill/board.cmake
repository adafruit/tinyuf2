set(JLINK_DEVICE stm32f401cc)

function(update_board TARGET)
  target_sources(${TARGET} PUBLIC
    ${ST_CMSIS}/Source/Templates/gcc/startup_stm32f401xc.s
    )
  target_compile_definitions(${TARGET} PUBLIC
    STM32F401xC
    HSE_VALUE=25000000U
    )
endfunction()
