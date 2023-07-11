cmake_minimum_required(VERSION 3.17)

include(${CMAKE_CURRENT_LIST_DIR}/../family_support.cmake)

project(tinyuf2 C ASM)

#------------------------------------
# TinyUF2
#------------------------------------

set(CMAKE_EXECUTABLE_SUFFIX .elf)

add_executable(tinyuf2
  board_flash.c
  boards.c
  romapi_flash.c
  #${TOP}/lib/tinyusb/src/portable/chipidea/ci_hs/dcd_ci_hs.c
  )

#target_link_options(tinyuf2 PUBLIC
#  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/linker/${MCU_VARIANT}_ram.ld"
#  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/linker/memory.ld"
#  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/linker/common.ld"
#  )

#family_configure_common(tinyuf2)
#add_board_target(board_${BOARD})
#
#include(${TOP}/src/tinyuf2.cmake)
#add_tinyuf2(tinyuf2)
#
#target_link_libraries(tinyuf2 PUBLIC board_${BOARD})
#
#family_flash_sdp(tinyuf2)
#family_flash_jlink(tinyuf2 hex)

family_configure_tinyuf2(tinyuf2)

#------------------------------------
# Application (including self update)
#------------------------------------

