include_guard(GLOBAL)

function(family_configure_app TARGET)
  family_configure_common(${TARGET})
  target_link_options(${TARGET} PUBLIC
    "LINKER:--script=${CMAKE_CURRENT_FUNCTION_LIST_DIR}/linker/stm32h5_app.ld"
    )
endfunction()
