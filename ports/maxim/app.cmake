include_guard(GLOBAL)

function(family_configure_app TARGET)
  family_configure_common(${TARGET})
  target_link_options(${TARGET} PUBLIC
    "LINKER:--script=${CMAKE_CURRENT_FUNCTION_LIST_DIR}/linker/${MAX_DEVICE}/${MAX_DEVICE}_app.ld"
    "LINKER:--script=${CMAKE_CURRENT_FUNCTION_LIST_DIR}/linker/${MAX_DEVICE}/${MAX_DEVICE}_common.ld"
    )
endfunction()
