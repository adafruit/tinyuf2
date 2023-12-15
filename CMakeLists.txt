cmake_minimum_required(VERSION 3.17)

include(ports/family_support.cmake)

# Espressif has its own build system
if(NOT FAMILY STREQUAL espressif)
  project(tinyuf2_all C ASM)
endif ()

add_subdirectory(ports/${FAMILY})
