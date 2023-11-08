include_guard()

if (NOT BOARD)
  message(FATAL_ERROR "BOARD not specified")
endif ()

#------------------------------------
# Config
#------------------------------------

set(UF2_FAMILY_ID 0x6b846188)
set(ST_HAL_DRIVER ${TOP}/lib/st/stm32f3xx_hal_driver)
set(ST_CMSIS ${TOP}/lib/st/cmsis_device_f3)
set(CMSIS_5 ${TOP}/lib/CMSIS_5)
set(PORT_DIR ${CMAKE_CURRENT_LIST_DIR})

include(${CMAKE_CURRENT_LIST_DIR}/boards/${BOARD}/board.cmake)

# enable LTO
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)

set(CMAKE_SYSTEM_PROCESSOR cortex-m4 CACHE INTERNAL "System Processor")
set(CMAKE_TOOLCHAIN_FILE ${TOP}/cmake/toolchain/arm_${TOOLCHAIN}.cmake)

#------------------------------------
# BOARD_TARGET
#------------------------------------
# used by all executable targets

function(add_board_target BOARD_TARGET)
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
    # nanolib
    --specs=nosys.specs
    --specs=nano.specs
    )
endfunction()

#------------------------------------
# Main target
#------------------------------------
function(family_configure_tinyuf2 TARGET)
  family_configure_common(${TARGET})
  add_board_target(board_${BOARD})

  #---------- Port Specific ----------
  target_sources(${TARGET} PUBLIC
    ${TOP}/lib/tinyusb/src/portable/st/stm32_fsdev/dcd_stm32_fsdev.c
    )
  #target_include_directories(${TARGET} PUBLIC)
  #target_compile_definitions(${TARGET} PUBLIC)
  target_link_options(${TARGET} PUBLIC
    "LINKER:--script=${CMAKE_CURRENT_FUNCTION_LIST_DIR}/linker/stm32f3_boot.ld"
    )

  include(${TOP}/src/tinyuf2.cmake)
  add_tinyuf2(${TARGET})

  target_link_libraries(${TARGET} PUBLIC board_${BOARD})
endfunction()
