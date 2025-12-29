set(MCU_VARIANT MIMXRT1176)

set(JLINK_DEVICE MIMXRT1176xxxA_M7)
set(PYOCD_TARGET mimxrt1170_cm7)
set(NXPLINK_DEVICE MIMXRT1176xxxxx:MIMXRT1170-EVK)

function(update_board TARGET)
  target_compile_definitions(${TARGET} PUBLIC
    CPU_MIMXRT1176DVMAA_cm7
    MIMXRT117x_SERIES
    )
endfunction()
