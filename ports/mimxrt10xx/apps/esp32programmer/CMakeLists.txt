#------------------------------------
# Application
# This file is meant to be include by add_subdirectory() in the root CMakeLists.txt
#------------------------------------
cmake_minimum_required(VERSION 3.17)

include(${CMAKE_CURRENT_LIST_DIR}/../../app.cmake)

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
