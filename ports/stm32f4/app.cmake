include_guard(GLOBAL)

function(family_configure_app TARGET)
  family_configure_common(${TARGET})
  target_compile_definitions(${TARGET} PUBLIC
    BUILD_APPLICATION
    )
  target_link_options(${TARGET} PUBLIC
    "LINKER:--script=${CMAKE_CURRENT_FUNCTION_LIST_DIR}/linker/stm32f4_app.ld"
    )

  family_gen_uf2(${TARGET} ${UF2_FAMILY_ID})
  family_flash_uf2(${TARGET} ${UF2_FAMILY_ID})
endfunction()
