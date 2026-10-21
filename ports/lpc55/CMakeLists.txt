cmake_minimum_required(VERSION 3.20)

include(${CMAKE_CURRENT_LIST_DIR}/../family_support.cmake)

project(tinyuf2 C ASM)
set(CMAKE_EXECUTABLE_SUFFIX .elf)

#------------------------------------
# TinyUF2
#------------------------------------
add_executable(tinyuf2
  boards.c
  ${TOP}/lib/tinyusb/src/portable/nxp/lpc_ip3511/dcd_lpc_ip3511.c
  )
target_link_options(tinyuf2 PUBLIC
  "LINKER:--script=${MCU_DIR}/gcc/${MCU_CORE}_flash.ld"
  )

family_configure_tinyuf2(tinyuf2 OPT_MCU_LPC55XX)
family_flash_jlink(tinyuf2)
family_flash_pyocd(tinyuf2)

#------------------------------------
# Application
#------------------------------------
family_add_app(blinky ${TOP}/apps/blinky)

# No self-update app: board_self_update() is not implemented for lpc55
