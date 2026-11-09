cmake_minimum_required(VERSION 3.17)
include(${CMAKE_CURRENT_LIST_DIR}/../family_support.cmake)
project(tinyuf2 C ASM)
set(CMAKE_EXECUTABLE_SUFFIX .elf)

add_executable(tinyuf2 boards.c board_flash.c dcd_ch32v4x7.c)
target_link_options(tinyuf2 PUBLIC
  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/linker/ch32v4x7_boot.ld"
)
# The port supplies its DCD without changing the pinned TinyUSB submodule.
family_configure_tinyuf2(tinyuf2 OPT_MCU_NONE)
