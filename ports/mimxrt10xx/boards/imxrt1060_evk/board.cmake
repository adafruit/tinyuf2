set(MCU_VARIANT MIMXRT1062)

set(JLINK_DEVICE MIMXRT1062xxx6A)
set(PYOCD_TARGET mimxrt1060)

function(update_board TARGET)
  target_compile_definitions(${TARGET} PUBLIC
    CPU_MIMXRT1062DVL6A
    )
endfunction()
