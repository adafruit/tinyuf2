include_guard()

if (NOT BOARD)
  message(FATAL_ERROR "BOARD not specified")
endif ()

#------------------------------------
# Config
#------------------------------------
set(UF2_FAMILY_ID 0x4fb2d5bd)
set(SDK_DIR ${TOP}/lib/nxp/mcux-sdk)
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
# "UF2 Write Address" shows where the image will reside in flash if you
# want to use a tool like pyocd to write the binary into flash through SWD
# Note: The .elf file cannot be written directly to flash since the target
# is RAM and the addresses need to be translated.
#---------------------------------------------------------
set(SDP_MIMXRT1011_PID 0x0145)
set(UF2_MIMXRT1011_WRITE_ADDR 0x60000400)

set(SDP_MIMXRT1015_PID 0x0130)
set(UF2_MIMXRT1015_WRITE_ADDR 0x60000000)

set(SDP_MIMXRT1021_PID 0x0130)
set(UF2_MIMXRT1021_WRITE_ADDR 0x60000000)

set(SDP_MIMXRT1024_PID 0x0130)
set(UF2_MIMXRT1024_WRITE_ADDR 0x60000000)

set(SDP_MIMXRT1042_PID 0x0135)
set(UF2_MIMXRT1042_WRITE_ADDR 0x60000000)

set(SDP_MIMXRT1052_PID 0x0130)
set(UF2_MIMXRT1052_WRITE_ADDR 0x60000000)

set(SDP_MIMXRT1062_PID 0x0135)
set(UF2_MIMXRT1062_WRITE_ADDR 0x60000000)

set(SDP_MIMXRT1064_PID 0x0135)
set(UF2_MIMXRT1064_WRITE_ADDR 0x70000000)

set(SDP_MIMXRT1176_PID 0x013d)
set(UF2_MIMXRT1176_WRITE_ADDR 0x30000000)

set(SDP_PID ${SDP_${MCU_VARIANT}_PID})
set(UF2_WRITE_ADDR ${UF2_${MCU_VARIANT}_WRITE_ADDR})

#------------------------------------
# BOARD_TARGET
#------------------------------------
# used by all executable targets
function(add_board_target BOARD_TARGET)
  if (TARGET ${BOARD_TARGET})
    return()
  endif ()

  add_library(${BOARD_TARGET} STATIC
    ${SDK_DIR}/devices/${MCU_VARIANT}/drivers/fsl_clock.c
    ${SDK_DIR}/devices/${MCU_VARIANT}/system_${MCU_VARIANT}.c
    ${SDK_DIR}/devices/${MCU_VARIANT}/gcc/startup_${MCU_VARIANT}.S
    ${SDK_DIR}/drivers/cache/armv7-m7/fsl_cache.c
    ${SDK_DIR}/drivers/common/fsl_common.c
    ${SDK_DIR}/drivers/igpio/fsl_gpio.c
    ${SDK_DIR}/drivers/lpuart/fsl_lpuart.c
    ${SDK_DIR}/drivers/ocotp/fsl_ocotp.c
    ${SDK_DIR}/drivers/pwm/fsl_pwm.c
    ${SDK_DIR}/drivers/xbara/fsl_xbara.c
    )
  target_include_directories(${BOARD_TARGET} PUBLIC
    # port & board
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/boards/${BOARD}
    # sdk
    ${CMSIS_DIR}/CMSIS/Core/Include
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

  update_board(${BOARD_TARGET})

  target_compile_definitions(${BOARD_TARGET} PUBLIC
    BOARD_UF2_FAMILY_ID=${UF2_FAMILY_ID}
    __ARMVFP__=0
    __ARMFPV5__=0
    XIP_EXTERNAL_FLASH=1
    XIP_BOOT_HEADER_ENABLE=1
    CFG_TUSB_MCU=OPT_MCU_MIMXRT
    )
  target_link_options(${BOARD_TARGET} PUBLIC
    --specs=nosys.specs
    --specs=nano.specs
    )
endfunction()

#------------------------------------
# override one in family_supoort.cmake
#------------------------------------

function(family_add_bin_hex TARGET)
  add_custom_command(TARGET ${TARGET} POST_BUILD
    COMMAND ${CMAKE_OBJCOPY} -Obinary $<TARGET_FILE:${TARGET}> $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.bin
    COMMAND ${CMAKE_OBJCOPY} -Oihex --change-addresses ${UF2_WRITE_ADDR} $<TARGET_FILE:${TARGET}> $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.hex
    VERBATIM)
endfunction()

function(family_flash_jlink TARGET)
  if (NOT DEFINED JLINKEXE)
    set(JLINKEXE JLinkExe)
  endif ()

  if (ARGC GREATER 1)
    set(BIN_FILE $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.${ARGV1})
  else ()
    set(BIN_FILE $<TARGET_FILE:${TARGET}>)
  endif ()

  file(GENERATE
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/${TARGET}.jlink
    CONTENT "halt
loadfile ${BIN_FILE}
r
go
exit"
    )

  add_custom_target(${TARGET}-jlink
    DEPENDS ${TARGET}
    COMMAND ${JLINKEXE} -device ${JLINK_DEVICE} -if swd -JTAGConf -1,-1 -speed auto -CommandFile ${CMAKE_CURRENT_BINARY_DIR}/${TARGET}.jlink
    )
endfunction()

function(family_flash_sdp TARGET)
  if (NOT DEFINED SDPHOST)
    set(SDPHOST sdphost)
  endif ()

  file(STRINGS ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/linker/${MCU_VARIANT}_ram.ld FCFB_ORIGIN
    REGEX "_fcfb_origin *="
    )
  file(STRINGS ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/linker/${MCU_VARIANT}_ram.ld IVT_ORIGIN
    REGEX "_ivt_origin *="
    )
  string(REGEX REPLACE ".*= *(0x[0-9a-fA-F]+).*" "\\1" FCFB_ORIGIN ${FCFB_ORIGIN})
  string(REGEX REPLACE ".*= *(0x[0-9a-fA-F]+).*" "\\1" IVT_ORIGIN ${IVT_ORIGIN})

  add_custom_target(${TARGET}-sdp
    DEPENDS ${TARGET}
    COMMAND ${SDPHOST} -u 0x1fc9,${SDP_PID} write-file ${FCFB_ORIGIN} $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.bin
    COMMAND ${SDPHOST} -u 0x1fc9,${SDP_PID} jump-address ${IVT_ORIGIN}
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
    ${TOP}/lib/tinyusb/src/portable/chipidea/ci_hs/dcd_ci_hs.c
    )
  #target_include_directories(${TARGET} PUBLIC)
  #target_compile_definitions(${TARGET} PUBLIC)
  target_link_options(${TARGET} PUBLIC
    "LINKER:--script=${CMAKE_CURRENT_FUNCTION_LIST_DIR}/linker/${MCU_VARIANT}_ram.ld"
    "LINKER:--script=${CMAKE_CURRENT_FUNCTION_LIST_DIR}/linker/memory.ld"
    "LINKER:--script=${CMAKE_CURRENT_FUNCTION_LIST_DIR}/linker/common.ld"
    )

  include(${TOP}/src/tinyuf2.cmake)
  add_tinyuf2(${TARGET})

  target_link_libraries(${TARGET} PUBLIC board_${BOARD})

  family_flash_sdp(${TARGET})
  family_flash_jlink(${TARGET} hex)
endfunction()
