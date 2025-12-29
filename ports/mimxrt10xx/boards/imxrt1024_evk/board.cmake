set(MCU_VARIANT MIMXRT1024)

set(JLINK_DEVICE MIMXRT1024DAG5A)
set(PYOCD_TARGET mimxrt1024)

function(update_board TARGET)
  target_compile_definitions(${TARGET} PUBLIC
    CPU_MIMXRT1024DAG5A
    )
endfunction()
