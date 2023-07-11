cmake_minimum_required(VERSION 3.17)

include(${CMAKE_CURRENT_LIST_DIR}/../family_support.cmake)

project(tinyuf2 C ASM)

#------------------------------------
# TinyUF2
#------------------------------------

set(CMAKE_EXECUTABLE_SUFFIX .elf)
add_executable(tinyuf2)

target_sources(tinyuf2 PUBLIC
  board_flash.c
  boards.c
  romapi_flash.c
  )
#target_compile_definitions(tinyuf2 PUBLIC)
#target_link_options(tinyuf2 PUBLIC)

family_configure_tinyuf2(tinyuf2)
