cmake_minimum_required(VERSION 3.17)

include(${CMAKE_CURRENT_LIST_DIR}/../family_support.cmake)

project(tinyuf2 C ASM)
set(CMAKE_EXECUTABLE_SUFFIX .elf)

#------------------------------------
# TinyUF2
#------------------------------------
add_executable(tinyuf2
  boards.c
  )
target_link_options(tinyuf2 PUBLIC
  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/linker/${CH32_FAMILY}_boot.ld"
  )

family_configure_tinyuf2(tinyuf2 OPT_MCU_CH32V20X)
target_sources(tinyuf2-tinyusb PUBLIC
  ${TOP}/lib/tinyusb/src/portable/st/stm32_fsdev/dcd_stm32_fsdev.c
  ${TOP}/lib/tinyusb/src/portable/wch/dcd_ch32_usbfs.c
  )
family_flash_openocd_wch(tinyuf2)

#------------------------------------
# Application (e.g self update)
#------------------------------------
#add_subdirectory(${CMAKE_CURRENT_LIST_DIR}/apps/self_update)
