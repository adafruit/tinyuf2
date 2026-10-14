cmake_minimum_required(VERSION 3.20)

include(${CMAKE_CURRENT_LIST_DIR}/../family_support.cmake)

project(tinyuf2 C ASM)
set(CMAKE_EXECUTABLE_SUFFIX .elf)

#------------------------------------
# TinyUF2
#------------------------------------
add_executable(tinyuf2
  boards.c
  ${TOP}/lib/tinyusb/src/portable/template/dcd_template.c
  )
# target_link_options(tinyuf2 PUBLIC "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/linker/<mcu>_boot.ld")

family_configure_tinyuf2(tinyuf2 OPT_MCU_NONE)
family_flash_jlink(tinyuf2)

#------------------------------------
# Application
#------------------------------------
# family_add_app(blinky ${TOP}/apps/blinky)   # with an app.cmake defining family_configure_app()
