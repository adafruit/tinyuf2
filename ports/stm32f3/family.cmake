include_guard()

#------------------------------------
# Config
#------------------------------------

set(UF2_FAMILY_ID 0x6b846188)
set(ST_HAL_DRIVER ${TOP}/lib/mcu/st/stm32f3xx_hal_driver)
set(ST_CMSIS ${TOP}/lib/mcu/st/cmsis_device_f3)
set(CMSIS_5 ${TOP}/lib/CMSIS_5)

include(${CMAKE_CURRENT_LIST_DIR}/boards/${BOARD}/board.cmake)

# enable LTO
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)

set(CMAKE_SYSTEM_PROCESSOR cortex-m4 CACHE INTERNAL "System Processor")
set(CMAKE_TOOLCHAIN_FILE ${TOP}/cmake/toolchain/arm_${TOOLCHAIN}.cmake)


#------------------------------------
# BOARD_TARGET
#------------------------------------
# used by all executable targets

function(family_add_board_target BOARD_TARGET)
  if (TARGET ${BOARD_TARGET})
    return()
  endif ()

  add_library(${BOARD_TARGET} STATIC
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
  target_include_directories(${BOARD_TARGET} PUBLIC
    # port & board
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/boards/${BOARD}
    # sdk
    ${CMSIS_5}/CMSIS/Core/Include
    ${ST_CMSIS}/Include
    ${ST_HAL_DRIVER}/Inc
    )

  update_board(${BOARD_TARGET})

  target_compile_definitions(${BOARD_TARGET} PUBLIC
    CFG_TUSB_MCU=OPT_MCU_STM32F3
    BOARD_UF2_FAMILY_ID=${UF2_FAMILY_ID}
    )
  target_compile_options(${BOARD_TARGET} PUBLIC
    )
  target_link_options(${BOARD_TARGET} PUBLIC
    -nostartfiles
    --specs=nosys.specs --specs=nano.specs
    )
endfunction()
