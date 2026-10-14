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
  ${TOP}/lib/tinyusb/src/portable/nxp/khci/dcd_khci.c
  )
target_link_options(tinyuf2 PUBLIC
  "LINKER:--script=${MCU_DIR}/gcc/${LD_FNAME}"
  )

family_configure_tinyuf2(tinyuf2 OPT_MCU_K32L2BXX)
family_flash_pyocd(tinyuf2)
