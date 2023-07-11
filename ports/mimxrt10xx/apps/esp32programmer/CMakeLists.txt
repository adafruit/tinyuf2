#------------------------------------
# Application
# This file is meant to be include by add_subdirectory() in the root CMakeLists.txt
#------------------------------------
cmake_minimum_required(VERSION 3.17)

set(APPLICATION_ADDR 0x6000C000)

# override bin hex output
function(family_add_bin_hex TARGET)
  add_custom_command(TARGET ${TARGET} POST_BUILD
    COMMAND ${CMAKE_OBJCOPY} -O binary -R .flash_config -R .ivt $<TARGET_FILE:${TARGET}> $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.bin
    COMMAND ${CMAKE_OBJCOPY} -Oihex -R .flash_config -R .ivt $<TARGET_FILE:${TARGET}> $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.hex
    VERBATIM)
endfunction()

#------------------------------------
# Application
#------------------------------------
add_executable(esp32programmer
  main.c
  usb_descriptors.c
  ${CMAKE_CURRENT_LIST_DIR}/../../boards.c
  ${TOP}/lib/tinyusb/src/portable/chipidea/ci_hs/dcd_ci_hs.c
  )
target_include_directories(esp32programmer PUBLIC
  .
  ${TOP}/src
  )
target_link_options(esp32programmer PUBLIC
  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/../../linker/${MCU_VARIANT}_ram.ld"
  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/../memory.ld"
  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/../../linker/common.ld"
  )

family_configure_common(esp32programmer)

target_link_libraries(esp32programmer PUBLIC board_${BOARD})
family_add_tinyusb(esp32programmer OPT_MCU_MIMXRT1XXX none)

family_add_uf2(esp32programmer ${UF2_FAMILY_ID})
family_flash_uf2(esp32programmer ${UF2_FAMILY_ID})
