#------------------------------------
# Application
# This file is meant to be include by add_subdirectory() in the root CMakeLists.txt
#------------------------------------
cmake_minimum_required(VERSION 3.17)

include(${FAMILY_PATH}/app.cmake)

add_executable(blinky
  src/blinky.c
  ${FAMILY_PATH}/boards.c
#  ${FAMILY_PATH}/board_flash.c
  )
target_include_directories(blinky PUBLIC
  ${TOP}/src
  )
target_compile_definitions(blinky PUBLIC
  BUILD_APPLICATION
  BUILD_NO_TINYUSB
  )

family_configure_app(blinky)
family_gen_uf2(blinky ${UF2_FAMILY_ID})
family_flash_uf2(blinky ${UF2_FAMILY_ID})
