#------------------------------------
# Application
# This file is meant to be include by add_subdirectory() in the root CMakeLists.txt
#------------------------------------
cmake_minimum_required(VERSION 3.17)

include(${CMAKE_CURRENT_LIST_DIR}/../app.cmake)

#------------------------------------
# Application
#------------------------------------
add_executable(erase_firmware
  ${TOP}/apps/erase_firmware/erase_firmware.c
  ${CMAKE_CURRENT_LIST_DIR}/../../boards.c
  )
target_include_directories(erase_firmware PUBLIC
  ${TOP}/src
  )
target_compile_definitions(erase_firmware PUBLIC
  BUILD_NO_TINYUSB
  )

configure_app(erase_firmware)
