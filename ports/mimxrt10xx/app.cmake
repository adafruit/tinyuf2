include_guard(GLOBAL)

# override bin hex output
function(family_gen_bin_hex TARGET)
  add_custom_command(TARGET ${TARGET} POST_BUILD
    COMMAND ${CMAKE_OBJCOPY} -O binary -R .flash_config -R .ivt $<TARGET_FILE:${TARGET}> $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.bin
    COMMAND ${CMAKE_OBJCOPY} -Oihex $<TARGET_FILE:${TARGET}> $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.hex
    VERBATIM)
endfunction()

function(family_configure_app TARGET)
  family_configure_common(${TARGET})
  target_compile_definitions(${TARGET} PUBLIC
    BUILD_APPLICATION
    )
  target_link_options(${TARGET} PUBLIC
    "LINKER:--script=${CMAKE_CURRENT_FUNCTION_LIST_DIR}/linker/${MCU_VARIANT}_ram.ld"
    "LINKER:--script=${CMAKE_CURRENT_FUNCTION_LIST_DIR}/linker/app.ld"
    "LINKER:--script=${CMAKE_CURRENT_FUNCTION_LIST_DIR}/linker/common.ld"
    )

  family_gen_uf2(${TARGET} ${UF2_FAMILY_ID})
  family_flash_uf2(${TARGET} ${UF2_FAMILY_ID})
endfunction()
