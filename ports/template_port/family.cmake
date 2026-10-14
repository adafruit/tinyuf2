include_guard(GLOBAL)

#------------------------------------
# Config
#------------------------------------

set(UF2_FAMILY_ID 0x00000000)

include(${CMAKE_CURRENT_LIST_DIR}/boards/${BOARD}/board.cmake)

# enable LTO
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)

set(CMAKE_SYSTEM_PROCESSOR cortex-m3 CACHE INTERNAL "System Processor")
set(CMAKE_TOOLCHAIN_FILE ${TOP}/cmake/toolchain/arm_${TOOLCHAIN}.cmake)

#------------------------------------
# BOARD_TARGET
#------------------------------------
# MCU SDK sources and includes shared by the bootloader and its apps
function(family_add_board_target BOARD_TARGET)
  if (TARGET ${BOARD_TARGET})
    return()
  endif ()

  add_library(${BOARD_TARGET} INTERFACE)
  target_include_directories(${BOARD_TARGET} INTERFACE
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/boards/${BOARD}
    )

  update_board(${BOARD_TARGET})

  target_compile_definitions(${BOARD_TARGET} INTERFACE
    BOARD_UF2_FAMILY_ID=${UF2_FAMILY_ID}
    )
endfunction()
