set(MCU LPC55S69)
set(MCU_CORE ${MCU}_cm33_core0)
set(PYOCD_TARGET ${MCU})
set(JLINK_DEVICE LPC55S69_M33_0)

function(update_board TARGET)
  target_compile_definitions(${TARGET} PUBLIC
    CPU_LPC55S69JBD100_cm33_core0
    )
endfunction()
