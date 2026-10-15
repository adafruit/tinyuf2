#------------------------------------
# Application
# Standalone project, built by the port's family_add_app() or directly with -DBOARD=
#------------------------------------
cmake_minimum_required(VERSION 3.20)

include(${CMAKE_CURRENT_LIST_DIR}/../../../family_support.cmake)

project(factory_test_metro_sd C ASM)
set(CMAKE_EXECUTABLE_SUFFIX .elf)

include(${FAMILY_PATH}/app.cmake)

add_compile_definitions(BUILD_APPLICATION)

#------------------------------------
# Application
#------------------------------------
add_executable(factory_test_metro_sd
  arduino.c
  main.c
  usb_descriptors.c
  ${CMAKE_CURRENT_LIST_DIR}/../../boards.c
  ${TOP}/lib/tinyusb/src/portable/chipidea/ci_hs/dcd_ci_hs.c
  )
target_include_directories(factory_test_metro_sd PUBLIC
  .
  ${TOP}/src
  )

#include(${TOP}/lib/fatfs/CMakeLists.txt)
#add_fatfs(factory_test_metro_sd)

include(middleware-sdmmc/CMakeLists.txt)
add_sdmmc(factory_test_metro_sd)

family_configure_app(factory_test_metro_sd)
family_add_tinyusb(factory_test_metro_sd OPT_MCU_MIMXRT1XXX)
family_gen_uf2(factory_test_metro_sd ${UF2_FAMILY_ID})
family_flash_uf2(factory_test_metro_sd ${UF2_FAMILY_ID})
