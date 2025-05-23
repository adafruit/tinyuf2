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

# imxrt run entirely on SRAM and can update its self using uf2
family_gen_uf2_from_bin(tinyuf2 ${UF2_FAMILY_ID} ${UF2_ADDR})
family_flash_uf2(tinyuf2 ${UF2_FAMILY_ID})

# copy to ARTIFACT_PATH
add_custom_command(TARGET tinyuf2 POST_BUILD
  COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE_DIR:tinyuf2>/tinyuf2.uf2 ${ARTIFACT_PATH}/apps/update-tinyuf2.uf2
  VERBATIM)

#------------------------------------
# Application
#------------------------------------
add_subdirectory(${TOP}/apps/blinky ${CMAKE_BINARY_DIR}/apps/blinky)
add_subdirectory(${TOP}/apps/erase_firmware ${CMAKE_BINARY_DIR}/apps/erase_firmware)

if (BOARD STREQUAL metro_m7_1011)
  add_subdirectory(apps/esp32programmer)
  add_subdirectory(apps/factory_test)
elseif (BOARD STREQUAL metro_m7_1011_sd)
  add_subdirectory(apps/factory_test_metro_sd)
endif ()
