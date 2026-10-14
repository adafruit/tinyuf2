#------------------------------------
# Application
# Standalone project, built by the port's family_add_app() or directly with -DBOARD=
#------------------------------------
cmake_minimum_required(VERSION 3.20)

include(${CMAKE_CURRENT_LIST_DIR}/../../../family_support.cmake)

project(factory_test C ASM)
set(CMAKE_EXECUTABLE_SUFFIX .elf)

include(${FAMILY_PATH}/app.cmake)

add_compile_definitions(BUILD_APPLICATION)

#------------------------------------
# Application
#------------------------------------
add_executable(factory_test
  arduino.c
  main.c
  wifi_scan.c
  ${TOP}/lib/mcu/nxp/mcux-sdk/drivers/common/fsl_common_arm.c
  usb_descriptors.c
  ${CMAKE_CURRENT_LIST_DIR}/../../boards.c
  ${TOP}/lib/tinyusb/src/portable/chipidea/ci_hs/dcd_ci_hs.c
  )
target_include_directories(factory_test PUBLIC
  .
  ${TOP}/src
  )

family_configure_app(factory_test)
family_add_tinyusb(factory_test OPT_MCU_MIMXRT1XXX)
family_gen_uf2(factory_test ${UF2_FAMILY_ID})
family_flash_uf2(factory_test ${UF2_FAMILY_ID})
