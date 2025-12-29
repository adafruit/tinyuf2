set(MCU_VARIANT MIMXRT1052)

set(JLINK_DEVICE MIMXRT1052xxxxB)
set(PYOCD_TARGET mimxrt1052)

function(update_board TARGET)

  target_compile_definitions(${TARGET} PUBLIC
    CPU_MIMXRT1052DVL6B
    )
endfunction()
