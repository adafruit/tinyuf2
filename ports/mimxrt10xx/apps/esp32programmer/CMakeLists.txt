#------------------------------------
# Application
# Standalone project, built by the port's family_add_app() or directly with -DBOARD=
#------------------------------------
cmake_minimum_required(VERSION 3.20)

include(${CMAKE_CURRENT_LIST_DIR}/../../../family_support.cmake)

project(esp32programmer C ASM)
set(CMAKE_EXECUTABLE_SUFFIX .elf)

include(${FAMILY_PATH}/app.cmake)

add_compile_definitions(BUILD_APPLICATION)

add_executable(esp32programmer
  main.c
  usb_descriptors.c
  ${CMAKE_CURRENT_LIST_DIR}/../../boards.c
  ${TOP}/lib/tinyusb/src/portable/chipidea/ci_hs/dcd_ci_hs.c
  )
target_include_directories(esp32programmer PUBLIC
  .
  ${TOP}/src
  )

family_configure_app(esp32programmer)
family_add_tinyusb(esp32programmer OPT_MCU_MIMXRT1XXX)
family_gen_uf2(esp32programmer ${UF2_FAMILY_ID})
family_flash_uf2(esp32programmer ${UF2_FAMILY_ID})
