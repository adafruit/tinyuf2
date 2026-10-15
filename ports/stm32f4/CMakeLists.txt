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
  ${TOP}/lib/tinyusb/src/portable/synopsys/dwc2/dcd_dwc2.c
  ${TOP}/lib/tinyusb/src/portable/synopsys/dwc2/dwc2_common.c
  )
target_link_options(tinyuf2 PUBLIC
  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/linker/stm32f4_boot.ld"
  )

family_configure_tinyuf2(tinyuf2 OPT_MCU_STM32F4)
family_flash_jlink(tinyuf2 hex)
family_flash_stlink(tinyuf2)

#------------------------------------
# Application
#------------------------------------
family_add_app(update-tinyuf2 ${TOP}/apps/self_update SELF_UPDATE)
family_add_app(blinky ${TOP}/apps/blinky)
family_add_app(erase_firmware ${TOP}/apps/erase_firmware)
