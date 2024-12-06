#------------------------------------
# This file is meant to be include by add_subdirectory() in the root CMakeLists.txt
#------------------------------------

# self_update target
add_executable(blinky
  ${TOP}/apps/blinky/blinky.c
  ${CMAKE_CURRENT_LIST_DIR}/../../boards.c
  ${CMAKE_CURRENT_LIST_DIR}/../../board_flash.c
  )
target_include_directories(blinky PUBLIC
  ${TOP}/src
  )
target_compile_definitions(blinky PUBLIC
  BUILD_NO_TINYUSB
  BUILD_APPLICATION
  )
target_link_options(blinky PUBLIC
  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/../../linker/stm32h5_app.ld"
  )

family_configure_common(blinky)
family_add_uf2(blinky ${UF2_FAMILY_ID})
family_flash_uf2(blinky ${UF2_FAMILY_ID})
