# The following five lines of boilerplate have to be in your project's
# CMakeLists in this exact order for cmake to work correctly
cmake_minimum_required(VERSION 3.5)

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

include(${CMAKE_SOURCE_DIR}/boards/${BOARD}/board.cmake)

# TOP is absolute path to root directory
set(TOP "../..")
get_filename_component(TOP "${TOP}" REALPATH)

set(EXTRA_COMPONENT_DIRS "${TOP}/src" boards)

set(SDKCONFIG_DEFAULTS sdkconfig.defaults boards/${BOARD}/sdkconfig)
set(SDKCONFIG ${CMAKE_BINARY_DIR}/sdkconfig)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)

execute_process(COMMAND git describe --dirty --always --tags
                OUTPUT_VARIABLE GIT_VERSION)
string(STRIP ${GIT_VERSION} GIT_VERSION)

execute_process(COMMAND bash "-c" "git submodule status ${TOP}/lib/esp-idf ${TOP}/lib/tinyusb | cut -d\" \" -f3,4 | paste -s -d\" \" -"
                OUTPUT_VARIABLE GIT_SUBMODULE_VERSIONS)
string(REPLACE ../../../../lib/ "" GIT_SUBMODULE_VERSIONS ${GIT_SUBMODULE_VERSIONS})
string(STRIP ${GIT_SUBMODULE_VERSIONS} GIT_SUBMODULE_VERSIONS)

add_compile_definitions(UF2_VERSION_BASE="${GIT_VERSION}")
add_compile_definitions(UF2_VERSION="${GIT_VERSION} - ${GIT_SUBMODULE_VERSIONS}")

project(tinyuf2)
