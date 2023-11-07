# The following five lines of boilerplate have to be in your project's
# CMakeLists in this exact order for cmake to work correctly
cmake_minimum_required(VERSION 3.17)

# BOARD must already be set
if (NOT DEFINED BOARD)
  message(FATAL_ERROR "BOARD must be set")
endif ()

include(${CMAKE_CURRENT_LIST_DIR}/../../../../family_support.cmake)
include(${CMAKE_SOURCE_DIR}/../../../boards/${BOARD}/board.cmake)

# Must be set before including IDF project.cmake
set(EXTRA_COMPONENT_DIRS "../../../boards" "../..")

set(SELFUPDATE_BUILD 1)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

#add_compile_definitions(TINYUF2_SELF_UPDATE)

project(update-tinyuf2)

idf_build_set_property(COMPILE_DEFINITIONS "TINYUF2_SELF_UPDATE" APPEND)
