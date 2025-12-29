set(MCU_VARIANT MIMXRT1021)

set(JLINK_DEVICE MIMXRT1021DAG5A)
set(PYOCD_TARGET mimxrt1020)

function(update_board TARGET)
  target_compile_definitions(${TARGET} PUBLIC
    CPU_MIMXRT1021DAG5A
    )
endfunction()
