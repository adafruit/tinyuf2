include_guard(GLOBAL)

#------------------------------------
# Config
#------------------------------------

set(UF2_FAMILY_ID 0x7f83e793)
set(SDK_DIR ${TOP}/lib/mcu/nxp/mcux-sdk)
set(CMSIS_5 ${TOP}/lib/CMSIS_5)

include(${CMAKE_CURRENT_LIST_DIR}/boards/${BOARD}/board.cmake)
set(MCU_DIR ${SDK_DIR}/devices/${MCU})

# enable LTO
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)

set(CMAKE_SYSTEM_PROCESSOR cortex-m0plus CACHE INTERNAL "System Processor")
set(CMAKE_TOOLCHAIN_FILE ${TOP}/cmake/toolchain/arm_${TOOLCHAIN}.cmake)

#------------------------------------
# BOARD_TARGET
#------------------------------------
function(family_add_board_target BOARD_TARGET)
  if (TARGET ${BOARD_TARGET})
    return()
  endif ()

  add_library(${BOARD_TARGET} STATIC
    ${MCU_DIR}/gcc/startup_${MCU}.S
    ${MCU_DIR}/system_${MCU}.c
    ${MCU_DIR}/drivers/fsl_clock.c
    ${SDK_DIR}/drivers/gpio/fsl_gpio.c
    ${SDK_DIR}/drivers/flash/fsl_ftfx_controller.c
    ${SDK_DIR}/drivers/flash/fsl_ftfx_flash.c
    ${SDK_DIR}/drivers/flash/fsl_ftfx_cache.c
    ${SDK_DIR}/drivers/flash/fsl_ftfx_flexnvm.c
    ${SDK_DIR}/drivers/lpuart/fsl_lpuart.c
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/clock_config.c
    )
  target_include_directories(${BOARD_TARGET} PUBLIC
    # port & board
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/boards/${BOARD}
    # sdk
    ${CMSIS_5}/CMSIS/Core/Include
    ${MCU_DIR}
    ${MCU_DIR}/drivers
    ${SDK_DIR}/drivers/smc
    ${SDK_DIR}/drivers/rtc
    ${SDK_DIR}/drivers/common
    ${SDK_DIR}/drivers/gpio
    ${SDK_DIR}/drivers/port
    ${SDK_DIR}/drivers/lpuart
    ${SDK_DIR}/drivers/flash
    )

  update_board(${BOARD_TARGET})

  target_compile_definitions(${BOARD_TARGET} PUBLIC
    BOARD_UF2_FAMILY_ID=${UF2_FAMILY_ID}
    )
  target_link_options(${BOARD_TARGET} PUBLIC
    --specs=nosys.specs --specs=nano.specs
    )
endfunction()
