set(MCU LPC55S28)
set(MCU_CORE ${MCU})
set(PYOCD_TARGET ${MCU})
set(JLINK_DEVICE LPC55S28JBD100)

function(update_board TARGET)
  target_compile_definitions(${TARGET} PUBLIC
    CPU_LPC55S28JBD100
    )
endfunction()
