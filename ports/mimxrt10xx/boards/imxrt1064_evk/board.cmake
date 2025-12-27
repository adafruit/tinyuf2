set(MCU_VARIANT MIMXRT1064)

set(JLINK_DEVICE MIMXRT1064xxx6A)
set(PYOCD_TARGET mimxrt1064)

function(update_board TARGET)
  target_sources(${TARGET} PRIVATE
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/clock_config.c
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/flash_config.c
    )
  target_compile_definitions(${TARGET} PUBLIC
    CPU_MIMXRT1064DVL6A
    )
endfunction()
