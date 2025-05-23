#------------------------------------
# Application
# This file is meant to be include by add_subdirectory() in the root CMakeLists.txt
#------------------------------------
cmake_minimum_required(VERSION 3.17)

include(${FAMILY_PATH}/app.cmake)

# Generate bootloader_bin.c
add_custom_command(OUTPUT bootloader_bin.c
  COMMAND ${Python_EXECUTABLE} ${UF2CONV_PY} --carray -o ${CMAKE_CURRENT_BINARY_DIR}/bootloader_bin.c $<TARGET_FILE_DIR:tinyuf2>/tinyuf2.bin
  DEPENDS tinyuf2
  )

add_executable(self_update
  self_update.c
  ${FAMILY_PATH}/boards.c
  ${FAMILY_PATH}/board_flash.c
  ${CMAKE_CURRENT_BINARY_DIR}/bootloader_bin.c
  )

target_include_directories(self_update PUBLIC
  ${TOP}/src
  )
target_compile_definitions(self_update PUBLIC
  TINYUF2_SELF_UPDATE
  BUILD_NO_TINYUSB
  BUILD_APPLICATION
  )

family_configure_app(self_update)
family_gen_uf2(self_update ${UF2_FAMILY_ID})
family_flash_uf2(self_update ${UF2_FAMILY_ID})
