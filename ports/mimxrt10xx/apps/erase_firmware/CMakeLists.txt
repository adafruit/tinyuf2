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
  )
target_include_directories(erase_firmware PUBLIC
  ${TOP}/src
  )

configure_app(erase_firmware)
target_link_libraries(erase_firmware PUBLIC board_${BOARD})
