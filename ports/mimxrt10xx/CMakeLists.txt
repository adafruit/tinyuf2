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
  ${TOP}/lib/tinyusb/src/portable/chipidea/ci_hs/dcd_ci_hs.c
  )
target_link_options(tinyuf2 PUBLIC
  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/linker/${MCU_VARIANT}_ram.ld"
  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/linker/memory.ld"
  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/linker/common.ld"
  )

# add board target
add_board_target(board_${BOARD})
target_link_libraries(tinyuf2 PUBLIC board_${BOARD})

family_configure_common(tinyuf2)

# Add tinyusb target
family_add_tinyusb(tinyuf2 OPT_MCU_MIMXRT1XXX none)

# Add tinyuf2
include(${TOP}/src/tinyuf2.cmake)
add_tinyuf2(tinyuf2)

family_flash_sdp(tinyuf2)
family_flash_jlink(tinyuf2 hex)

#------------------------------------
# Application (including self update)
#------------------------------------

add_subdirectory(apps/esp32programmer)
