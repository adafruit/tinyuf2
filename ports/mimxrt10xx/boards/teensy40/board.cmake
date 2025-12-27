set(MCU_VARIANT MIMXRT1062)

set(PYOCD_TARGET mimxrt1060)

function(update_board TARGET)
  target_sources(${TARGET} PRIVATE
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/clock_config.c
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/flash_config.c
    )
  target_compile_definitions(${TARGET} PUBLIC
    CPU_MIMXRT1062DVL6A
    )
endfunction()
