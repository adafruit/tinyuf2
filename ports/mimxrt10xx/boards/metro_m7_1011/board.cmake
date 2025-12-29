set(MCU_VARIANT MIMXRT1011)

set(JLINK_DEVICE MIMXRT1011DAE5A)
set(PYOCD_TARGET mimxrt1010)
set(NXPLINK_DEVICE MIMXRT1011xxxxx:EVK-MIMXRT1010)

function(update_board TARGET)

  target_compile_definitions(${TARGET} PUBLIC
    CPU_MIMXRT1011DAE5A
    )
endfunction()
