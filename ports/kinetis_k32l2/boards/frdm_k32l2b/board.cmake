set(MCU K32L2B31A)
set(LD_FNAME K32L2B31xxxxA_flash.ld)
set(PYOCD_TARGET K32L2B3)

function(update_board TARGET)
  target_compile_definitions(${TARGET} PUBLIC
    CPU_K32L2B31VLH0A
    )
endfunction()
