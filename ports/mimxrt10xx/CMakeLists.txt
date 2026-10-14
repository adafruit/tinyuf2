cmake_minimum_required(VERSION 3.20)

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
  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/linker/boot.ld"
  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/linker/common.ld"
  )

family_configure_tinyuf2(tinyuf2 OPT_MCU_MIMXRT1XXX)

family_flash_sdp(tinyuf2)
family_flash_jlink(tinyuf2 hex)

# erase first 64KB to ensure clean state for UF2 update
math(EXPR ERASE_END_ADDR "( ${FLASH_BASE} + 0x10000 )" OUTPUT_FORMAT HEXADECIMAL)
family_jlink_erase_external(tinyuf2 ${FLASH_BASE} ${ERASE_END_ADDR})

# imxrt run entirely on SRAM and can update its self using uf2
family_gen_uf2_from_bin(tinyuf2 ${UF2_FAMILY_ID} ${FLASH_FCFB_ADDR})
family_flash_uf2(tinyuf2 ${UF2_FAMILY_ID})

# copy to ARTIFACT_PATH
add_custom_command(TARGET tinyuf2 POST_BUILD
  COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE_DIR:tinyuf2>/tinyuf2.uf2 ${ARTIFACT_PATH}/apps/update-tinyuf2.uf2
  BYPRODUCTS ${ARTIFACT_PATH}/apps/update-tinyuf2.uf2
  VERBATIM)

#------------------------------------
# Application
#------------------------------------
family_add_app(blinky ${TOP}/apps/blinky)
family_add_app(erase_firmware ${TOP}/apps/erase_firmware)
family_add_app(dfu_runtime ${CMAKE_CURRENT_LIST_DIR}/apps/dfu_runtime)
family_add_app(esp32programmer ${CMAKE_CURRENT_LIST_DIR}/apps/esp32programmer BOARDS metro_m7_1011)
family_add_app(factory_test ${CMAKE_CURRENT_LIST_DIR}/apps/factory_test BOARDS metro_m7_1011)
family_add_app(factory_test_metro_sd ${CMAKE_CURRENT_LIST_DIR}/apps/factory_test_metro_sd BOARDS metro_m7_1011_sd)
