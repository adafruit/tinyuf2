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
  ${TOP}/lib/tinyusb/src/portable/st/stm32_fsdev/dcd_stm32_fsdev.c
  ${TOP}/lib/tinyusb/src/portable/st/stm32_fsdev/fsdev_common.c
  )
target_link_options(tinyuf2 PUBLIC
  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/linker/stm32h5_boot.ld"
  )

family_configure_tinyuf2(tinyuf2 OPT_MCU_STM32H5)
family_flash_jlink(tinyuf2)
family_flash_stlink(tinyuf2 hex)

#------------------------------------
# Application
#------------------------------------
family_add_app(update-tinyuf2 ${TOP}/apps/self_update SELF_UPDATE)
family_add_app(blinky ${TOP}/apps/blinky)
family_add_app(erase_firmware ${TOP}/apps/erase_firmware)
