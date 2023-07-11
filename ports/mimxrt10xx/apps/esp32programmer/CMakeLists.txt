#------------------------------------
# Application
# This file is meant to be include by add_subdirectory() in the root CMakeLists.txt
#------------------------------------
cmake_minimum_required(VERSION 3.17)

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

target_link_libraries(esp32programmer PUBLIC board_${BOARD})
family_add_tinyusb(esp32programmer OPT_MCU_MIMXRT1XXX none)
