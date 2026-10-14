#------------------------------------
# Application
# Standalone project, built by the port's family_add_app(SELF_UPDATE) or directly with -DBOARD= -DBOOTLOADER_BIN=
#------------------------------------
cmake_minimum_required(VERSION 3.20)

include(${CMAKE_CURRENT_LIST_DIR}/../../ports/family_support.cmake)

project(update-tinyuf2 C ASM)
set(CMAKE_EXECUTABLE_SUFFIX .elf)

if (NOT DEFINED BOOTLOADER_BIN)
  message(FATAL_ERROR "BOOTLOADER_BIN (the bootloader's tinyuf2.bin) not specified")
endif ()

include(${FAMILY_PATH}/app.cmake)

add_compile_definitions(
  TINYUF2_SELF_UPDATE
  BUILD_NO_TINYUSB
  BUILD_APPLICATION
  )

add_custom_command(OUTPUT bootloader_bin.c
  COMMAND ${Python_EXECUTABLE} ${UF2CONV_PY} --carray -o ${CMAKE_CURRENT_BINARY_DIR}/bootloader_bin.c ${BOOTLOADER_BIN}
  DEPENDS ${BOOTLOADER_BIN} ${UF2CONV_PY}
  )

add_executable(update-tinyuf2
  self_update.c
  ${FAMILY_PATH}/boards.c
  ${FAMILY_PATH}/board_flash.c
  ${CMAKE_CURRENT_BINARY_DIR}/bootloader_bin.c
  )
target_include_directories(update-tinyuf2 PUBLIC
  ${TOP}/src
  )

family_configure_app(update-tinyuf2)
family_gen_uf2(update-tinyuf2 ${UF2_FAMILY_ID})
family_flash_uf2(update-tinyuf2 ${UF2_FAMILY_ID})
