cmake_minimum_required(VERSION 3.17)

include(${CMAKE_CURRENT_LIST_DIR}/../family_support.cmake)

project(tinyuf2 C ASM)
set(CMAKE_EXECUTABLE_SUFFIX .elf)

#------------------------------------
# TinyUF2
#------------------------------------
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

family_configure_tinyuf2(tinyuf2 OPT_MCU_MIMXRT1XXX)

family_flash_sdp(tinyuf2)
family_flash_jlink(tinyuf2 hex)
family_add_uf2(tinyuf2 ${UF2_FAMILY_ID} bin ${UF2_ADDR})
family_flash_uf2(tinyuf2 ${UF2_FAMILY_ID})

#------------------------------------
# Application (e.g self update)
#------------------------------------
add_subdirectory(apps/erase_firmware)

if (BOARD STREQUAL metro_m7_1011)
  add_subdirectory(apps/esp32programmer)
  add_subdirectory(apps/factory_test)
elseif (BOARD STREQUAL metro_m7_1011_sd)
  add_subdirectory(apps/factory_test_metro_sd)
endif ()
