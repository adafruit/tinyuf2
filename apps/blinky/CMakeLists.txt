#------------------------------------
# Application
# Standalone project, built by the port's family_add_app() or directly with -DBOARD=
#------------------------------------
cmake_minimum_required(VERSION 3.20)

include(${CMAKE_CURRENT_LIST_DIR}/../../ports/family_support.cmake)

project(blinky C ASM)
set(CMAKE_EXECUTABLE_SUFFIX .elf)

include(${FAMILY_PATH}/app.cmake)

add_compile_definitions(
  BUILD_APPLICATION
  BUILD_NO_TINYUSB
  )

add_executable(blinky
  src/blinky.c
  ${FAMILY_PATH}/boards.c
  )
target_include_directories(blinky PUBLIC
  ${TOP}/src
  )

family_configure_app(blinky)
family_gen_uf2(blinky ${UF2_FAMILY_ID})
family_flash_uf2(blinky ${UF2_FAMILY_ID})
