cmake_minimum_required(VERSION 3.17)

#------------------------------------
# Config
#------------------------------------
include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/family_support.cmake)
set(ST_HAL_DRIVER ${TOP}/lib/st/stm32f3xx_hal_driver)
set(ST_CMSIS ${TOP}/lib/st/cmsis_device_f3)
set(CMSIS_5 ${TOP}/lib/CMSIS_5)
set(PORT_DIR ${CMAKE_CURRENT_LIST_DIR})

include(${CMAKE_CURRENT_LIST_DIR}/boards/${BOARD}/board.cmake)

# enable LTO for all targets
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)

set(CMAKE_SYSTEM_PROCESSOR cortex-m4 CACHE INTERNAL "System Processor")
set(CMAKE_TOOLCHAIN_FILE ${TOP}/cmake/toolchain/arm_${TOOLCHAIN}.cmake)

set(UF2_FAMILY_ID 0x6b846188)

project(tinyuf2 C ASM)

#------------------------------------
# TinyUF2
#------------------------------------

add_executable(tinyuf2)
family_configure(tinyuf2)

target_sources(tinyuf2 PUBLIC
  board_flash.c
  boards.c
  boards.h
  # tinyusb port
  ${TOP}/lib/tinyusb/src/portable/st/stm32_fsdev/dcd_stm32_fsdev.c
  )
target_include_directories(tinyuf2 PUBLIC
  .
  )
target_compile_options(tinyuf2 PUBLIC
  )
target_link_options(tinyuf2 PUBLIC
  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/linker/stm32f3_boot.ld"
  )

include(${CMAKE_CURRENT_SOURCE_DIR}/../../src/tinyuf2.cmake)
add_tinyuf2(tinyuf2)

# include tinyusb cmake
#include(${CMAKE_CURRENT_SOURCE_DIR}/../lib/tinyusb/src/CMakeLists.txt)

target_link_libraries(tinyuf2 board_${BOARD})

family_add_bin_hex(tinyuf2)
family_flash_jlink(tinyuf2)

# Self Update
add_subdirectory(${CMAKE_CURRENT_SOURCE_DIR}/apps/self_update)

#------------------------------------
# BOARD_TARGET
#------------------------------------

# used by all executable
add_library(board_${BOARD} STATIC
  ${ST_CMSIS}/Source/Templates/system_stm32f3xx.c
  ${ST_HAL_DRIVER}/Src/stm32f3xx_hal.c
  ${ST_HAL_DRIVER}/Src/stm32f3xx_hal_cortex.c
  ${ST_HAL_DRIVER}/Src/stm32f3xx_hal_rcc.c
  ${ST_HAL_DRIVER}/Src/stm32f3xx_hal_rcc_ex.c
  ${ST_HAL_DRIVER}/Src/stm32f3xx_hal_gpio.c
  ${ST_HAL_DRIVER}/Src/stm32f3xx_hal_flash.c
  ${ST_HAL_DRIVER}/Src/stm32f3xx_hal_flash_ex.c
  ${ST_HAL_DRIVER}/Src/stm32f3xx_hal_uart.c
  )
target_include_directories(board_${BOARD} PUBLIC
  .
  boards/${BOARD}
  ${CMSIS_5}/CMSIS/Core/Include
  ${ST_CMSIS}/Include
  ${ST_HAL_DRIVER}/Inc
  )
target_compile_definitions(board_${BOARD} PUBLIC
  CFG_TUSB_MCU=OPT_MCU_STM32F3
  BOARD_UF2_FAMILY_ID=${UF2_FAMILY_ID}
  )
target_compile_options(board_${BOARD} PUBLIC
  )
target_link_options(board_${BOARD} PUBLIC
  -nostartfiles
  # nanolib
  --specs=nosys.specs
  --specs=nano.specs
  )

# board specific
update_board(board_${BOARD})
