set(MCU_VARIANT MIMXRT1042)

set(JLINK_DEVICE MIMXRT1042xxx5B)
set(PYOCD_TARGET mimxrt1042)

function(update_board TARGET)

  target_compile_definitions(${TARGET} PUBLIC
    CPU_MIMXRT1042XJM5B
    )
endfunction()
