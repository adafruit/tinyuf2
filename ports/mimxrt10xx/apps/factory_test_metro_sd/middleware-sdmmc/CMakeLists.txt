include_guard(GLOBAL)

function(add_sdmmc TARGET)
  target_sources(${TARGET} PUBLIC
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/sdspi/fsl_sdspi.c
    )

  target_include_directories(${TARGET} PUBLIC
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/sdspi
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/common
    )
endfunction()
