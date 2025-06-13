#------------------------------------
# Application
# This file is meant to be include by add_subdirectory() in the root CMakeLists.txt
#------------------------------------
cmake_minimum_required(VERSION 3.17)

include(${FAMILY_PATH}/app.cmake)

add_executable(erase_firmware
  src/erase_firmware.c
  ${FAMILY_PATH}/boards.c
  )
target_include_directories(erase_firmware PUBLIC
  ${TOP}/src
  )
target_compile_definitions(erase_firmware PUBLIC
  BUILD_APPLICATION
  BUILD_NO_TINYUSB
  )

family_configure_app(erase_firmware)
family_gen_uf2(erase_firmware ${UF2_FAMILY_ID})
family_flash_uf2(erase_firmware ${UF2_FAMILY_ID})
