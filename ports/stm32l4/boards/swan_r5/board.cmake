set(JLINK_DEVICE stm32l4r5zi)

function(update_board TARGET)
  target_sources(${TARGET} PUBLIC
    ${ST_CMSIS}/Source/Templates/gcc/startup_stm32l4r5xx.s
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/board.c
    )
  # board.c includes board_api.h
  target_include_directories(${TARGET} PUBLIC
    ${TOP}/src
    )
  target_compile_definitions(${TARGET} PUBLIC
    STM32L4R5xx
    LSE_VALUE=32768U
    )
endfunction()
