#------------------------------------
# Application
# Standalone project, built by the port's family_add_app() or directly with -DBOARD=
#------------------------------------
cmake_minimum_required(VERSION 3.20)

include(${CMAKE_CURRENT_LIST_DIR}/../../ports/family_support.cmake)

project(erase_firmware C ASM)
set(CMAKE_EXECUTABLE_SUFFIX .elf)

include(${FAMILY_PATH}/app.cmake)

add_compile_definitions(
  BUILD_APPLICATION
  BUILD_NO_TINYUSB
  )

add_executable(erase_firmware
  src/erase_firmware.c
  ${FAMILY_PATH}/boards.c
  )
target_include_directories(erase_firmware PUBLIC
  ${TOP}/src
  )

family_configure_app(erase_firmware)
family_gen_uf2(erase_firmware ${UF2_FAMILY_ID})
family_flash_uf2(erase_firmware ${UF2_FAMILY_ID})
