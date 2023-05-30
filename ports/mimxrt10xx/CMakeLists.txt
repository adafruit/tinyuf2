cmake_minimum_required(VERSION 3.17)
include(CMakePrintHelpers)

set(TOOLCHAIN gcc)
include(family.cmake)

project(tinyuf2 C ASM)

# Bootloader
add_executable(tinyuf2)

family_configure_target(tinyuf2)

target_sources(tinyuf2 PUBLIC
  ${CMAKE_CURRENT_SOURCE_DIR}/board_flash.c
  ${CMAKE_CURRENT_SOURCE_DIR}/boards.c
  ${CMAKE_CURRENT_SOURCE_DIR}/romapi_flash.c
  )

include(${CMAKE_CURRENT_SOURCE_DIR}/../../src/tinyuf2.cmake)
add_tinyuf2(tinyuf2)

# include tinyusb cmake
#include(${CMAKE_CURRENT_SOURCE_DIR}/../lib/tinyusb/src/CMakeLists.txt)