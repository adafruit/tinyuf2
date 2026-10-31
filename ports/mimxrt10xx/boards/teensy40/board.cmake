set(MCU_VARIANT MIMXRT1062)

set(PYOCD_TARGET mimxrt1060)
set(TEENSY_MCU TEENSY40)

function(update_board TARGET)

  target_compile_definitions(${TARGET} PUBLIC
    CPU_MIMXRT1062DVL6A
    )
endfunction()
