include_guard(GLOBAL)

if (BOARD_PFLASH_APP_EN)
  # Apps run from internal flash at BOARD_FLASH_APP_START, boards.c points VTOR at their vector table
  set(APP_LOCATION PFLASH_APP)
else ()
  # Apps are loaded into AXISRAM by the bootloader and run from there: the vector table too, from the
  # board library's system_stm32h7xx.c
  add_compile_definitions(VECT_TAB_SRAM)
  set(APP_LOCATION RAMCODE)
endif ()

function(family_configure_app TARGET)
  family_configure_common(${TARGET})
  target_sources(${TARGET} PRIVATE
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/board_flash.c
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/board_hmi.c
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/board_irq.c
    )
  # before the scripts: the MCU's layout picks the app origin with DEFINED(RAMCODE) or DEFINED(PFLASH_APP)
  target_link_options(${TARGET} PUBLIC
    "LINKER:--defsym=${APP_LOCATION}=0"
    )
  family_add_linker_scripts(${TARGET})
endfunction()
