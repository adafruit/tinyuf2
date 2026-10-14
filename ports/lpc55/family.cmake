include_guard(GLOBAL)

#------------------------------------
# Config
#------------------------------------

set(UF2_FAMILY_ID 0x2abc77ec)
set(SDK_DIR ${TOP}/lib/mcu/nxp/mcux-sdk)
set(CMSIS_5 ${TOP}/lib/CMSIS_5)

include(${CMAKE_CURRENT_LIST_DIR}/boards/${BOARD}/board.cmake)
set(MCU_DIR ${SDK_DIR}/devices/${MCU})

# enable LTO
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)

set(CMAKE_SYSTEM_PROCESSOR cortex-m33 CACHE INTERNAL "System Processor")
set(CMAKE_TOOLCHAIN_FILE ${TOP}/cmake/toolchain/arm_${TOOLCHAIN}.cmake)

#------------------------------------
# BOARD_TARGET
#------------------------------------
function(family_add_board_target BOARD_TARGET)
  if (TARGET ${BOARD_TARGET})
    return()
  endif ()

  add_library(${BOARD_TARGET} STATIC
    ${MCU_DIR}/gcc/startup_${MCU_CORE}.S
    ${MCU_DIR}/system_${MCU_CORE}.c
    ${MCU_DIR}/project_template/clock_config.c
    ${MCU_DIR}/drivers/fsl_clock.c
    ${MCU_DIR}/drivers/fsl_power.c
    ${MCU_DIR}/drivers/fsl_reset.c
    ${SDK_DIR}/drivers/flexcomm/fsl_flexcomm.c
    ${SDK_DIR}/drivers/flexcomm/fsl_usart.c
    ${SDK_DIR}/drivers/iap1/fsl_iap.c
    ${SDK_DIR}/drivers/lpc_gpio/fsl_gpio.c
    ${SDK_DIR}/drivers/lpc_rtc/fsl_rtc.c
    )
  target_include_directories(${BOARD_TARGET} PUBLIC
    # port & board
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/boards/${BOARD}
    # sdk
    ${CMSIS_5}/CMSIS/Core/Include
    ${MCU_DIR}
    ${MCU_DIR}/project_template
    ${MCU_DIR}/drivers
    ${SDK_DIR}/drivers/common
    ${SDK_DIR}/drivers/flexcomm
    ${SDK_DIR}/drivers/iap1
    ${SDK_DIR}/drivers/lpc_gpio
    ${SDK_DIR}/drivers/lpc_iocon
    ${SDK_DIR}/drivers/lpc_rtc
    ${SDK_DIR}/drivers/sctimer
    )

  update_board(${BOARD_TARGET})

  target_compile_definitions(${BOARD_TARGET} PUBLIC
    BOARD_UF2_FAMILY_ID=${UF2_FAMILY_ID}
    )
  target_link_libraries(${BOARD_TARGET} PUBLIC
    ${MCU_DIR}/gcc/libpower_hardabi.a
    )
  target_link_options(${BOARD_TARGET} PUBLIC
    --specs=nosys.specs --specs=nano.specs
    )
endfunction()
