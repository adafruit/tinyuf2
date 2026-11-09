include_guard(GLOBAL)

set(SDK_DIR ${TOP}/lib/mcu/wch/ch32v4x7)
set(SDK_SRC_DIR ${SDK_DIR}/EVT/EXAM/SRC)
set(SDK_SYSTEM_DIR ${SDK_DIR}/EVT/EXAM/FLASH/FLASH_Program/User)
include(${CMAKE_CURRENT_LIST_DIR}/boards/${BOARD}/board.cmake)
set(CMAKE_SYSTEM_PROCESSOR rv32imac-ilp32 CACHE INTERNAL "System Processor")
set(CMAKE_TOOLCHAIN_FILE ${TOP}/cmake/toolchain/riscv_${TOOLCHAIN}.cmake)

function(family_add_board_target BOARD_TARGET)
  if(TARGET ${BOARD_TARGET})
    return()
  endif()
  add_library(${BOARD_TARGET} STATIC
    ${SDK_SRC_DIR}/Peripheral/src/ch32v4x7_flash.c
    ${SDK_SRC_DIR}/Peripheral/src/ch32v4x7_gpio.c
    ${SDK_SRC_DIR}/Peripheral/src/ch32v4x7_rcc.c
    ${SDK_SYSTEM_DIR}/system_ch32v4x7.c
    ${SDK_SRC_DIR}/Startup/startup_ch32v4x7.S
  )
  target_include_directories(${BOARD_TARGET} PUBLIC
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/boards/${BOARD}
    ${SDK_SRC_DIR}/Peripheral/inc
    ${SDK_SRC_DIR}/Core
    ${SDK_SYSTEM_DIR}
  )
  target_compile_definitions(${BOARD_TARGET} PUBLIC
    BOARD_UF2_FAMILY_ID=0x7b8c32a7
    HSE_VALUE=25000000
  )
  target_compile_options(${BOARD_TARGET} PUBLIC -mcmodel=medany -march=rv32imac_zicsr_zifencei)
  target_link_options(${BOARD_TARGET} PUBLIC
    -march=rv32imac_zicsr_zifencei
    -Wl,--defsym=__flash_size=524288
    -Wl,--defsym=__ram_size=204800
    -nostartfiles --specs=nosys.specs --specs=nano.specs
  )
endfunction()
