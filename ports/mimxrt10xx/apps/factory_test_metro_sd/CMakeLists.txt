#------------------------------------
# Application
# This file is meant to be include by add_subdirectory() in the root CMakeLists.txt
#------------------------------------
cmake_minimum_required(VERSION 3.17)

include(${CMAKE_CURRENT_LIST_DIR}/../app.cmake)

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

family_configure_common(factory_test_metro_sd)
configure_app(factory_test_metro_sd)

target_link_libraries(factory_test_metro_sd PUBLIC board_${BOARD})
family_add_tinyusb(factory_test_metro_sd OPT_MCU_MIMXRT1XXX none)
