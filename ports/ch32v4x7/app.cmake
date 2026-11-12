include_guard(GLOBAL)

function(family_configure_app TARGET)
  family_configure_common(${TARGET})
  target_link_options(${TARGET} PUBLIC
    "LINKER:--script=${CMAKE_CURRENT_FUNCTION_LIST_DIR}/linker/ch32v4x7_app.ld"
    "LINKER:--script=${CMAKE_CURRENT_FUNCTION_LIST_DIR}/linker/ch32v4x7_common.ld"
    )
endfunction()
