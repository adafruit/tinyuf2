# toolchain set up
set(CMAKE_SYSTEM_PROCESSOR cortex-m7 CACHE INTERNAL "System Processor")
set(CMAKE_TOOLCHAIN_FILE ${CMAKE_CURRENT_LIST_DIR}/../../cmake/toolchain/arm_${TOOLCHAIN}.cmake)

function(family_configure_target TARGET)
  if (NOT BOARD)
    message(FATAL_ERROR "BOARD not specified")
  endif ()

  set(SDK_DIR ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../../lib/nxp/mcux-sdk)

  # set output name to .elf
  set_target_properties(${TARGET} PROPERTIES OUTPUT_NAME ${TARGET}.elf)
  set_target_properties(${TARGET} PROPERTIES DEPS_SUBMODULES ${SDK_DIR})

  include(${CMAKE_CURRENT_FUNCTION_LIST_DIR}/boards/${BOARD}/board.cmake)

  set(UF2_FAMILY_ID 0x4fb2d5bd)

  target_compile_definitions(${TARGET} PUBLIC
    BOARD_UF2_FAMILY_ID=${UF2_FAMILY_ID}
    CFG_TUSB_MCU=OPT_MCU_MIMXRT
    __ARMVFP__=0
    __ARMFPV5__=0
    XIP_EXTERNAL_FLASH=1
    XIP_BOOT_HEADER_ENABLE=1
    )

  target_link_options(${TARGET} PUBLIC
    --specs=nosys.specs
    --specs=nano.specs
    )

  target_sources(${TARGET} PUBLIC
    # TinyUSB
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../../lib/tinyusb/src/portable/chipidea/ci_hs/dcd_ci_hs.c
    # BSP
    ${SDK_DIR}/devices/${MCU_VARIANT}/system_${MCU_VARIANT}.c
    ${SDK_DIR}/devices/${MCU_VARIANT}/drivers/fsl_clock.c
    ${SDK_DIR}/drivers/cache/armv7-m7/fsl_cache.c
    ${SDK_DIR}/drivers/common/fsl_common.c
    ${SDK_DIR}/drivers/igpio/fsl_gpio.c
    ${SDK_DIR}/drivers/lpuart/fsl_lpuart.c
    ${SDK_DIR}/drivers/ocotp/fsl_ocotp.c
    ${SDK_DIR}/drivers/pwm/fsl_pwm.c
    ${SDK_DIR}/drivers/xbara/fsl_xbara.c
    )

  if (TOOLCHAIN STREQUAL "gcc")
    target_sources(${TARGET} PUBLIC
      ${SDK_DIR}/devices/${MCU_VARIANT}/gcc/startup_${MCU_VARIANT}.S
      )

    target_link_options(${TARGET} PUBLIC
      "LINKER:--script=${CMAKE_CURRENT_FUNCTION_LIST_DIR}/linker/${MCU_VARIANT}_ram.ld"
      "LINKER:--script=${CMAKE_CURRENT_FUNCTION_LIST_DIR}/linker/memory.ld"
      "LINKER:--script=${CMAKE_CURRENT_FUNCTION_LIST_DIR}/linker/common.ld"
      )
  else ()
    # TODO support IAR
  endif ()

  target_include_directories(${TARGET} PUBLIC
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/boards/${BOARD}
    ${SDK_DIR}/CMSIS/Include
    ${SDK_DIR}/devices/${MCU_VARIANT}
    ${SDK_DIR}/devices/${MCU_VARIANT}/xip
    ${SDK_DIR}/devices/${MCU_VARIANT}/drivers
    ${SDK_DIR}/drivers/cache/armv7-m7
    ${SDK_DIR}/drivers/common
    ${SDK_DIR}/drivers/igpio
    ${SDK_DIR}/drivers/lpuart
    ${SDK_DIR}/drivers/ocotp
    ${SDK_DIR}/drivers/pwm
    ${SDK_DIR}/drivers/rtwdog
    ${SDK_DIR}/drivers/xbara
    ${SDK_DIR}/drivers/wdog01
    )
endfunction()
