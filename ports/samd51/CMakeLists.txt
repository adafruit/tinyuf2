cmake_minimum_required(VERSION 3.20)

include(${CMAKE_CURRENT_LIST_DIR}/../family_support.cmake)

project(tinyuf2 C ASM)
set(CMAKE_EXECUTABLE_SUFFIX .elf)

#------------------------------------
# TinyUF2
#------------------------------------
add_executable(tinyuf2
  board_flash.c
  boards.c
  ${TOP}/lib/tinyusb/src/portable/microchip/samd/dcd_samd.c
  )
target_link_options(tinyuf2 PUBLIC
  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/linker/samd51_boot.ld"
  )

family_configure_tinyuf2(tinyuf2 OPT_MCU_SAMD51)
family_flash_openocd(tinyuf2)

#------------------------------------
# Application
#------------------------------------
family_add_app(update-tinyuf2 ${TOP}/apps/self_update SELF_UPDATE)
family_add_app(blinky ${TOP}/apps/blinky)
