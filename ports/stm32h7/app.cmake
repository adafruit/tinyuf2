include_guard(GLOBAL)

# Apps are loaded into AXISRAM by the bootloader and run from there: the vector table too, from the
# board library's system_stm32h7xx.c
add_compile_definitions(VECT_TAB_SRAM)

function(family_configure_app TARGET)
  family_configure_common(${TARGET})
  target_sources(${TARGET} PRIVATE
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/board_flash.c
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/board_irq.c
    )
  # before the scripts: h750xx.ld picks the AXISRAM origin with DEFINED(RAMCODE)
  target_link_options(${TARGET} PUBLIC
    "LINKER:--defsym=RAMCODE=0"
    )
  family_add_linker_scripts(${TARGET})
endfunction()
