include_guard()

function(add_fatfs TARGET)
  target_sources(${TARGET} PUBLIC
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/source/ff.c
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/source/ffsystem.c
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/source/ffunicode.c
    )

  target_include_directories(${TARGET} PUBLIC
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/source
    )
endfunction()
