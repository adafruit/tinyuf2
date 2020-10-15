# The following five lines of boilerplate have to be in your project's
# CMakeLists in this exact order for cmake to work correctly
cmake_minimum_required(VERSION 3.5)

# hack default to espressif_saola_1_wrover for quick testing
if(NOT (DEFINED BOARD))
  set(BOARD espressif_saola_1_wrover)
endif()

# Check for -DBOARD=
if(NOT (DEFINED BOARD AND EXISTS "${CMAKE_SOURCE_DIR}/boards/${BOARD}/board.h") )
  file(GLOB BOARD_LIST RELATIVE ${CMAKE_SOURCE_DIR}/boards "boards/*/board.h")
  
  message("Please specify `-DBOARD=` with one of supported boards")
  foreach(board IN LISTS BOARD_LIST)
    string(REPLACE "/board.h" "" board ${board})
    message("- ${board}")
  endforeach()
  
  message(FATAL_ERROR "Invalid BOARD specified")
endif()

# TOP is absolute path to root directory
set(TOP "../..")
get_filename_component(TOP "${TOP}" REALPATH)

set(EXTRA_COMPONENT_DIRS "${TOP}/src" boards)

set(SDKCONFIG_DEFAULTS sdkconfig.defaults boards/${BOARD}/sdkconfig)
set(SDKCONFIG build/sdkconfig)
 
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
set(SUPPORTED_TARGETS esp32s2)

project(uf2-esp32s)
