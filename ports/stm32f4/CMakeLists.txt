cmake_minimum_required(VERSION 3.17)

include(${CMAKE_CURRENT_LIST_DIR}/../family_support.cmake)

project(tinyuf2 C ASM)
set(CMAKE_EXECUTABLE_SUFFIX .elf)

#------------------------------------
# TinyUF2
#------------------------------------
add_executable(tinyuf2
  board_flash.c
  boards.c
  ${TOP}/lib/tinyusb/src/portable/synopsys/dwc2/dcd_dwc2.c
  ${TOP}/lib/tinyusb/src/portable/synopsys/dwc2/dwc2_common.c
  )
target_link_options(tinyuf2 PUBLIC
  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/linker/stm32f4_boot.ld"
  )

family_configure_tinyuf2(tinyuf2 OPT_MCU_STM32F4)
family_flash_jlink(tinyuf2)
family_flash_stlink(tinyuf2)

#------------------------------------
# Application
#------------------------------------
add_subdirectory(${TOP}/apps/self_update ${CMAKE_BINARY_DIR}/apps/self_update)
add_subdirectory(${TOP}/apps/blinky ${CMAKE_BINARY_DIR}/apps/blinky)
add_subdirectory(${TOP}/apps/erase_firmware ${CMAKE_BINARY_DIR}/apps/erase_firmware)
