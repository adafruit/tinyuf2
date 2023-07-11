cmake_minimum_required(VERSION 3.17)

include(${CMAKE_CURRENT_LIST_DIR}/family_support.cmake)

project(tinyuf2_all C ASM)

add_subdirectory(${FAMILY})
