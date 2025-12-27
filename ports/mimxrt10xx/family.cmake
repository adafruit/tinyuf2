include_guard(GLOBAL)

set(UF2_FAMILY_ID 0x4fb2d5bd)
set(SDK_DIR ${TOP}/lib/mcu/nxp/mcux-sdk)
set(CMSIS_DIR ${TOP}/lib/CMSIS_5)

include(${CMAKE_CURRENT_LIST_DIR}/boards/${BOARD}/board.cmake)

set(CMAKE_SYSTEM_PROCESSOR cortex-m7 CACHE INTERNAL "System Processor")
set(CMAKE_TOOLCHAIN_FILE ${CMAKE_CURRENT_LIST_DIR}/../../cmake/toolchain/arm_${TOOLCHAIN}.cmake)

#---------------------------------------------------------
# Load to SRAM using sdphost
# Note: you may need to give the sdphost binary executable permission first.
#
# SDP loads the image into the RAM locations specified in the .ld files.
#  - "SDP Write Address" must equal _fcfb_origin
#  - "SDP Jump Address" must equal _ivt_origin
#
# TinyUF2 will copy itself to the correct location in flash.
# "UF2 Address" shows where the image will reside in flash if you
# want to use a tool like pyocd to write the binary into flash through SWD
# Note: The .elf file cannot be written directly to flash since the target
# is RAM and the addresses need to be translated.
#---------------------------------------------------------
if (NOT DEFINED SDPHOST)
  set(SDPHOST sdphost)
endif ()

if (NOT DEFINED BLHOST)
  set(BLHOST blhost)
endif ()

set(SDP_MIMXRT1011_PID 0x0145)
set(SDP_MIMXRT1015_PID 0x0130)
set(SDP_MIMXRT1021_PID 0x0130)
set(SDP_MIMXRT1024_PID 0x0130)
set(SDP_MIMXRT1042_PID 0x0135)
set(SDP_MIMXRT1052_PID 0x0130)
set(SDP_MIMXRT1062_PID 0x0135)
set(SDP_MIMXRT1064_PID 0x0135)
set(SDP_MIMXRT1176_PID 0x013d)

set(SDP_PID ${SDP_${MCU_VARIANT}_PID})

cmake_print_variables(MCU_VARIANT)

file(STRINGS ${CMAKE_CURRENT_LIST_DIR}/linker/${MCU_VARIANT}_ram.ld FCFB_ORIGIN REGEX "_fcfb_origin *=")
string(REGEX REPLACE ".*= *(0x[0-9a-fA-F]+).*" "\\1" FCFB_ORIGIN ${FCFB_ORIGIN})
file(STRINGS ${CMAKE_CURRENT_LIST_DIR}/linker/${MCU_VARIANT}_ram.ld FLASH_BASE REGEX "_flash_base *=")
string(REGEX REPLACE ".*= *(0x[0-9a-fA-F]+).*" "\\1" FLASH_BASE ${FLASH_BASE})
math(EXPR IVT_ORIGIN "( ${FCFB_ORIGIN} & ~0xFFF ) + 0x1000" OUTPUT_FORMAT HEXADECIMAL)
math(EXPR FLASH_FCFB_ADDR "( ${FLASH_BASE} + (${FCFB_ORIGIN} & 0xFFF) )" OUTPUT_FORMAT HEXADECIMAL)

cmake_print_variables(FCFB_ORIGIN IVT_ORIGIN FLASH_FCFB_ADDR)

#------------------------------------
# BOARD_TARGET
#------------------------------------
# used by all executable targets
function(family_add_board_target BOARD_TARGET)
  if (TARGET ${BOARD_TARGET})
    return()
  endif ()

  # Common sources for all MIMXRT variants
  add_library(${BOARD_TARGET} STATIC
    ${SDK_DIR}/devices/${MCU_VARIANT}/drivers/fsl_clock.c
    ${SDK_DIR}/drivers/common/fsl_common.c
    ${SDK_DIR}/drivers/igpio/fsl_gpio.c
    ${SDK_DIR}/drivers/lpspi/fsl_lpspi.c
    ${SDK_DIR}/drivers/lpuart/fsl_lpuart.c
    ${SDK_DIR}/drivers/ocotp/fsl_ocotp.c
    ${SDK_DIR}/drivers/pwm/fsl_pwm.c
    ${SDK_DIR}/drivers/xbara/fsl_xbara.c
    )

  # ROM API is present on most parts except RT1011.
  if (NOT MCU_VARIANT STREQUAL "MIMXRT1011")
    target_sources(${BOARD_TARGET} PRIVATE
      ${SDK_DIR}/devices/${MCU_VARIANT}/drivers/fsl_romapi.c
    )
  endif ()

  # Common include directories
  target_include_directories(${BOARD_TARGET} PUBLIC
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/boards/${BOARD}
    ${CMSIS_DIR}/CMSIS/Core/Include
    ${SDK_DIR}/devices/${MCU_VARIANT}
    ${SDK_DIR}/devices/${MCU_VARIANT}/xip
    ${SDK_DIR}/devices/${MCU_VARIANT}/drivers
    ${SDK_DIR}/drivers/common
    ${SDK_DIR}/drivers/igpio
    ${SDK_DIR}/drivers/lpspi
    ${SDK_DIR}/drivers/lpuart
    ${SDK_DIR}/drivers/ocotp
    ${SDK_DIR}/drivers/pwm
    ${SDK_DIR}/drivers/rtwdog
    ${SDK_DIR}/drivers/xbara
    ${SDK_DIR}/drivers/wdog01
    )

  # MCU-specific sources and includes
  if (MCU_VARIANT STREQUAL "MIMXRT1176")
    # MIMXRT1176 uses CM7-specific startup/system files
    target_sources(${BOARD_TARGET} PRIVATE
      ${SDK_DIR}/devices/${MCU_VARIANT}/system_${MCU_VARIANT}_cm7.c
      ${SDK_DIR}/devices/${MCU_VARIANT}/gcc/startup_${MCU_VARIANT}_cm7.S
      ${SDK_DIR}/devices/${MCU_VARIANT}/drivers/fsl_dcdc.c
      ${SDK_DIR}/devices/${MCU_VARIANT}/drivers/fsl_pmu.c
      ${SDK_DIR}/devices/${MCU_VARIANT}/drivers/fsl_anatop_ai.c
      ${SDK_DIR}/drivers/common/fsl_common_arm.c
      ${SDK_DIR}/devices/${MCU_VARIANT}/drivers/cm7/fsl_cache.c
      )
    target_include_directories(${BOARD_TARGET} PUBLIC
      ${SDK_DIR}/devices/${MCU_VARIANT}/drivers/cm7
      )
  else()
    # Other MIMXRT10xx variants
    target_sources(${BOARD_TARGET} PRIVATE
      ${SDK_DIR}/devices/${MCU_VARIANT}/system_${MCU_VARIANT}.c
      ${SDK_DIR}/devices/${MCU_VARIANT}/gcc/startup_${MCU_VARIANT}.S
      ${SDK_DIR}/drivers/adc_12b1msps_sar/fsl_adc.c
      ${SDK_DIR}/drivers/cache/armv7-m7/fsl_cache.c
      )
    target_include_directories(${BOARD_TARGET} PUBLIC
      ${SDK_DIR}/drivers/adc_12b1msps_sar
      ${SDK_DIR}/drivers/cache/armv7-m7
      )
  endif()

  update_board(${BOARD_TARGET})

  target_compile_definitions(${BOARD_TARGET} PUBLIC
    BOARD_UF2_FAMILY_ID=${UF2_FAMILY_ID}
    __ARMVFP__=0
    __ARMFPV5__=0
    XIP_EXTERNAL_FLASH=1
    XIP_BOOT_HEADER_ENABLE=1
    )
  target_link_options(${BOARD_TARGET} PUBLIC
    --specs=nosys.specs --specs=nano.specs
    )
endfunction()

#------------------------------------
# override one in family_supoort.cmake
#------------------------------------
function(family_gen_bin_hex TARGET)
  add_custom_command(TARGET ${TARGET} POST_BUILD
    COMMAND ${CMAKE_OBJCOPY} -Obinary $<TARGET_FILE:${TARGET}> $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.bin
    COMMAND ${CMAKE_OBJCOPY} -Ibinary -Oihex --change-addresses ${FLASH_FCFB_ADDR} $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.bin $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.hex
    VERBATIM)
endfunction()

function(family_flash_sdp TARGET)
  if (MCU_VARIANT STREQUAL "MIMXRT1176")
    # Create a ROM load-image friendly binary with IVT at file offset 0.
    add_custom_command(TARGET ${TARGET} POST_BUILD
      COMMAND python3 ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/tools/make_ivt0_image.py $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.bin $<TARGET_FILE_DIR:${TARGET}>/tinyuf2_ivt0.bin
      VERBATIM
    )
    add_custom_target(${TARGET}-sdp
      DEPENDS ${TARGET}
      COMMAND ${BLHOST} -u 0x1fc9,${SDP_PID} load-image $<TARGET_FILE_DIR:${TARGET}>/tinyuf2_ivt0.bin
      VERBATIM
    )
  else ()
  add_custom_target(${TARGET}-sdp
    DEPENDS ${TARGET}
    COMMAND ${SDPHOST} -u 0x1fc9,${SDP_PID} write-file ${FCFB_ORIGIN} $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.bin
    COMMAND ${SDPHOST} -u 0x1fc9,${SDP_PID} jump-address ${IVT_ORIGIN}
    )
  endif ()
endfunction()
