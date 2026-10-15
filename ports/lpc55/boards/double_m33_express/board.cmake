set(MCU LPC55S69)
set(MCU_CORE ${MCU}_cm33_core0)
set(PYOCD_TARGET ${MCU})
set(JLINK_DEVICE LPC55S69_M33_0)

function(update_board TARGET)
  target_sources(${TARGET} PUBLIC
    ${TOP}/lib/sct_neopixel/sct_neopixel.c
    )
  target_include_directories(${TARGET} PUBLIC
    ${TOP}/lib/sct_neopixel
    )
  target_compile_definitions(${TARGET} PUBLIC
    CPU_LPC55S69JBD100_cm33_core0
    )
endfunction()
