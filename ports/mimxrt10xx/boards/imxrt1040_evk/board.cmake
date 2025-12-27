set(MCU_VARIANT MIMXRT1042)

set(JLINK_DEVICE MIMXRT1042xxx5B)
set(PYOCD_TARGET mimxrt1042)

function(update_board TARGET)
  target_sources(${TARGET} PRIVATE
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/clock_config.c
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/flash_config.c
    )
  target_compile_definitions(${TARGET} PUBLIC
    CPU_MIMXRT1042XJM5B
    )
endfunction()
