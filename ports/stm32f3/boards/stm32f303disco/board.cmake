#set(MCU_VARIANT MIMXRT1011)
set(JLINK_DEVICE stm32f303vc)

function(update_board TARGET)
  target_sources(${TARGET} PUBLIC
    ${ST_CMSIS}/Source/Templates/gcc/startup_stm32f303xc.s
    )
  target_compile_definitions(${TARGET} PUBLIC
    STM32F303xC
    HSE_VALUE=8000000U
    )
endfunction()
