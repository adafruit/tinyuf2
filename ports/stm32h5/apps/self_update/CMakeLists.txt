#------------------------------------
# Self Update
# This file is meant to be include by add_subdirectory() in the root CMakeLists.txt
#------------------------------------

# Generate bootloader_bin.c
add_custom_command(OUTPUT bootloader_bin.c
  COMMAND ${Python_EXECUTABLE} ${UF2CONV_PY} --carray -o bootloader_bin.c $<TARGET_FILE_DIR:tinyuf2>/tinyuf2.bin
  DEPENDS tinyuf2
  )

# self_update target
add_executable(self_update
  ${TOP}/apps/self_update/self_update.c
  ${CMAKE_CURRENT_LIST_DIR}/../../boards.c
  ${CMAKE_CURRENT_LIST_DIR}/../../board_flash.c
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
target_link_options(self_update PUBLIC
  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/../../linker/stm32h5_app.ld"
  )

family_configure_common(self_update)
family_add_uf2(self_update ${UF2_FAMILY_ID})
family_flash_uf2(self_update ${UF2_FAMILY_ID})
