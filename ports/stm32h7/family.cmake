include_guard(GLOBAL)

#------------------------------------
# Config
#------------------------------------

set(UF2_FAMILY_ID 0x6db66082)
set(ST_HAL_DRIVER ${TOP}/lib/mcu/st/stm32h7xx_hal_driver)
set(ST_CMSIS ${TOP}/lib/mcu/st/cmsis_device_h7)
set(CMSIS_5 ${TOP}/lib/CMSIS_5)
set(GIT_SUBMODULES tinyusb uf2)

include(${CMAKE_CURRENT_LIST_DIR}/boards/${BOARD}/board.cmake)

# LTO is off unless -DLTO_ON=1, as in make
if (LTO_ON)
  set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)
else ()
  set(CMAKE_INTERPROCEDURAL_OPTIMIZATION FALSE)
endif ()

set(CMAKE_SYSTEM_PROCESSOR cortex-m7 CACHE INTERNAL "System Processor")
set(CMAKE_TOOLCHAIN_FILE ${TOP}/cmake/toolchain/arm_${TOOLCHAIN}.cmake)

#------------------------------------
# BOARD_TARGET
#------------------------------------
function(family_add_board_target BOARD_TARGET)
  if (TARGET ${BOARD_TARGET})
    return()
  endif ()

  add_library(${BOARD_TARGET} STATIC
    ${ST_CMSIS}/Source/Templates/system_stm32h7xx.c
    ${ST_HAL_DRIVER}/Src/stm32h7xx_hal.c
    ${ST_HAL_DRIVER}/Src/stm32h7xx_hal_cortex.c
    ${ST_HAL_DRIVER}/Src/stm32h7xx_hal_rcc.c
    ${ST_HAL_DRIVER}/Src/stm32h7xx_hal_rcc_ex.c
    ${ST_HAL_DRIVER}/Src/stm32h7xx_hal_gpio.c
    ${ST_HAL_DRIVER}/Src/stm32h7xx_hal_flash.c
    ${ST_HAL_DRIVER}/Src/stm32h7xx_hal_flash_ex.c
    ${ST_HAL_DRIVER}/Src/stm32h7xx_hal_uart.c
    ${ST_HAL_DRIVER}/Src/stm32h7xx_hal_spi.c
    ${ST_HAL_DRIVER}/Src/stm32h7xx_hal_pwr.c
    ${ST_HAL_DRIVER}/Src/stm32h7xx_hal_qspi.c
    ${ST_HAL_DRIVER}/Src/stm32h7xx_hal_mdma.c
    ${ST_HAL_DRIVER}/Src/stm32h7xx_hal_pwr_ex.c
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

  # external flash and display drivers selected by board.cmake, they include board_api.h
  set(COMPONENTS ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/components)
  if (DEFINED SPI_FLASH OR DEFINED QSPI_FLASH OR DEFINED DISPLAY_DRV)
    target_include_directories(${BOARD_TARGET} PUBLIC ${TOP}/src)
  endif ()
  if (SPI_FLASH STREQUAL W25Qx_SPI)
    target_sources(${BOARD_TARGET} PRIVATE ${COMPONENTS}/w25qxx/w25qxx.c)
    target_include_directories(${BOARD_TARGET} PUBLIC ${COMPONENTS}/w25qxx)
    target_link_libraries(${BOARD_TARGET} PUBLIC m) # w25qxx.c uses powf()
  endif ()
  if (QSPI_FLASH STREQUAL W25Qx_QSPI)
    target_sources(${BOARD_TARGET} PRIVATE ${COMPONENTS}/w25qxx/w25qxx_qspi.c)
    target_include_directories(${BOARD_TARGET} PUBLIC ${COMPONENTS}/w25qxx)
  elseif (QSPI_FLASH STREQUAL IS25LP064A)
    target_sources(${BOARD_TARGET} PRIVATE ${COMPONENTS}/is25lp064a/is25lp064a_qspi.c)
    target_include_directories(${BOARD_TARGET} PUBLIC ${COMPONENTS}/is25lp064a)
  endif ()
  if (DISPLAY_DRV STREQUAL ST7735)
    target_sources(${BOARD_TARGET} PRIVATE
      ${COMPONENTS}/st7735/st7735.c
      ${COMPONENTS}/st7735/fonts.c
      )
    target_include_directories(${BOARD_TARGET} PUBLIC ${COMPONENTS}/st7735)
  endif ()
  foreach (DRV SPI_FLASH QSPI_FLASH)
    if (DEFINED ${DRV})
      target_compile_definitions(${BOARD_TARGET} PUBLIC ${${DRV}})
    endif ()
  endforeach ()

  update_board(${BOARD_TARGET})

  target_compile_definitions(${BOARD_TARGET} PUBLIC
    BOARD_UF2_FAMILY_ID=${UF2_FAMILY_ID}
    )
  target_link_options(${BOARD_TARGET} PUBLIC
    --specs=nosys.specs --specs=nano.specs
    )
endfunction()

# memory.ld, common.ld then the MCU's layout, the order make links them in
function(family_add_linker_scripts TARGET)
  target_link_options(${TARGET} PUBLIC
    "LINKER:--script=${CMAKE_CURRENT_FUNCTION_LIST_DIR}/linker/memory.ld"
    "LINKER:--script=${CMAKE_CURRENT_FUNCTION_LIST_DIR}/linker/common.ld"
    "LINKER:--script=${CMAKE_CURRENT_FUNCTION_LIST_DIR}/linker/${MCU}.ld"
    )
endfunction()
