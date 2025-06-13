include_guard(GLOBAL)

#------------------------------------
# Config
#------------------------------------
set(MSDK_LIB ${TOP}/lib/mcu/analog/msdk/Libraries)

include(${CMAKE_CURRENT_LIST_DIR}/boards/${BOARD}/board.cmake)

# enable LTO
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)

set(CMAKE_SYSTEM_PROCESSOR cortex-m4 CACHE INTERNAL "System Processor")
set(CMAKE_TOOLCHAIN_FILE ${TOP}/cmake/toolchain/arm_${TOOLCHAIN}.cmake)

cmake_print_variables(MAX_DEVICE)
string(TOUPPER ${MAX_DEVICE} MAX_DEVICE_UPPER)

set(OPENOCD_OPTION "-f interface/cmsis-dap.cfg -f target/${MAX_DEVICE}.cfg")

set(UF2_FAMILY_ID_MAX32650 0xd63f8632)
set(UF2_FAMILY_ID_MAX32665 0xf0c30d71)
set(UF2_FAMILY_ID_MAX32666 ${UF2_FAMILY_ID_MAX32665})
set(UF2_FAMILY_ID_MAX32690 0x7410520a)
set(UF2_FAMILY_ID_MAX78002 0x91d3fd18)

set(UF2_FAMILY_ID ${UF2_FAMILY_ID_${MAX_DEVICE_UPPER}})

# 32KB
set(FLASH_BOOT_SIZE 0x8000)

if (${MAX_DEVICE} STREQUAL "max32650")
  set(PERIPH_ID 10)
  set(PERIPH_SUFFIX "me")
elseif (${MAX_DEVICE} STREQUAL "max32665" OR ${MAX_DEVICE} STREQUAL "max32666")
  set(PERIPH_ID 14)
  set(PERIPH_SUFFIX "me")
elseif (${MAX_DEVICE} STREQUAL "max32690")
  set(PERIPH_ID 18)
  set(PERIPH_SUFFIX "me")
elseif (${MAX_DEVICE} STREQUAL "max78002")
  set(PERIPH_ID 87)
  set(PERIPH_SUFFIX "ai")
else()
  message(FATAL_ERROR "Unsupported MAX device: ${MAX_DEVICE}")
endif()

#------------------------------------
# BOARD_TARGET
#------------------------------------
function(family_add_board_target BOARD_TARGET)
  if (TARGET ${BOARD_TARGET})
    return()
  endif ()

  # Common
  add_library(${BOARD_TARGET} STATIC
    ${MSDK_LIB}/CMSIS/Device/Maxim/${MAX_DEVICE_UPPER}/Source/GCC/startup_${MAX_DEVICE}.S
    ${MSDK_LIB}/CMSIS/Device/Maxim/${MAX_DEVICE_UPPER}/Source/heap.c
    ${MSDK_LIB}/CMSIS/Device/Maxim/${MAX_DEVICE_UPPER}/Source/system_${MAX_DEVICE}.c
    ${MSDK_LIB}/PeriphDrivers/Source/SYS/mxc_assert.c
    ${MSDK_LIB}/PeriphDrivers/Source/SYS/mxc_delay.c
    ${MSDK_LIB}/PeriphDrivers/Source/SYS/mxc_lock.c
    ${MSDK_LIB}/PeriphDrivers/Source/SYS/nvic_table.c
    ${MSDK_LIB}/PeriphDrivers/Source/SYS/pins_${PERIPH_SUFFIX}${PERIPH_ID}.c
    ${MSDK_LIB}/PeriphDrivers/Source/SYS/sys_${PERIPH_SUFFIX}${PERIPH_ID}.c
    ${MSDK_LIB}/PeriphDrivers/Source/FLC/flc_common.c
    ${MSDK_LIB}/PeriphDrivers/Source/FLC/flc_${PERIPH_SUFFIX}${PERIPH_ID}.c
    ${MSDK_LIB}/PeriphDrivers/Source/FLC/flc_reva.c
    ${MSDK_LIB}/PeriphDrivers/Source/GPIO/gpio_common.c
    ${MSDK_LIB}/PeriphDrivers/Source/GPIO/gpio_${PERIPH_SUFFIX}${PERIPH_ID}.c
    ${MSDK_LIB}/PeriphDrivers/Source/GPIO/gpio_reva.c
    ${MSDK_LIB}/PeriphDrivers/Source/ICC/icc_${PERIPH_SUFFIX}${PERIPH_ID}.c
    ${MSDK_LIB}/PeriphDrivers/Source/ICC/icc_reva.c
    ${MSDK_LIB}/PeriphDrivers/Source/UART/uart_common.c
    ${MSDK_LIB}/PeriphDrivers/Source/UART/uart_${PERIPH_SUFFIX}${PERIPH_ID}.c
    )
  target_include_directories(${BOARD_TARGET} PUBLIC
    # port & board
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/boards/${BOARD}
    # sdk
    ${MSDK_LIB}/CMSIS/5.9.0/Core/Include
    ${MSDK_LIB}/CMSIS/Device/Maxim/${MAX_DEVICE_UPPER}/Include
    ${MSDK_LIB}/PeriphDrivers/Include/${MAX_DEVICE_UPPER}
    ${MSDK_LIB}/PeriphDrivers/Source/SYS
    ${MSDK_LIB}/PeriphDrivers/Source/GPIO
    ${MSDK_LIB}/PeriphDrivers/Source/ICC
    ${MSDK_LIB}/PeriphDrivers/Source/FLC
    ${MSDK_LIB}/PeriphDrivers/Source/UART
    )

  # device specific
  if (${MAX_DEVICE} STREQUAL "max32650" OR
      ${MAX_DEVICE} STREQUAL "max32665" OR ${MAX_DEVICE} STREQUAL "max32666")
    target_sources(${BOARD_TARGET} PRIVATE
      ${MSDK_LIB}/PeriphDrivers/Source/ICC/icc_common.c
      ${MSDK_LIB}/PeriphDrivers/Source/TPU/tpu_${PERIPH_SUFFIX}${PERIPH_ID}.c
      ${MSDK_LIB}/PeriphDrivers/Source/TPU/tpu_reva.c
      ${MSDK_LIB}/PeriphDrivers/Source/UART/uart_reva.c
      )
    target_include_directories(${BOARD_TARGET} PUBLIC
      ${MSDK_LIB}/PeriphDrivers/Source/TPU
      )
  elseif (${MAX_DEVICE} STREQUAL "max32690")
    target_sources(${BOARD_TARGET} PRIVATE
      ${MSDK_LIB}/PeriphDrivers/Source/CTB/ctb_${PERIPH_SUFFIX}${PERIPH_ID}.c
      ${MSDK_LIB}/PeriphDrivers/Source/CTB/ctb_reva.c
      ${MSDK_LIB}/PeriphDrivers/Source/CTB/ctb_common.c
      ${MSDK_LIB}/PeriphDrivers/Source/UART/uart_revb.c
      )
    target_include_directories(${BOARD_TARGET} PUBLIC
      ${MSDK_LIB}/PeriphDrivers/Source/CTB
      )
  elseif (${MAX_DEVICE} STREQUAL "max78002")
    target_sources(${BOARD_TARGET} PRIVATE
      ${MSDK_LIB}/PeriphDrivers/Source/AES/aes_${PERIPH_SUFFIX}${PERIPH_ID}.c
      ${MSDK_LIB}/PeriphDrivers/Source/AES/aes_revb.c
      ${MSDK_LIB}/PeriphDrivers/Source/TRNG/trng_${PERIPH_SUFFIX}${PERIPH_ID}.c
      ${MSDK_LIB}/PeriphDrivers/Source/TRNG/trng_revb.c
      ${MSDK_LIB}/PeriphDrivers/Source/UART/uart_revb.c
      )
    target_include_directories(${BOARD_TARGET} PUBLIC
      ${MSDK_LIB}/PeriphDrivers/Source/AES
      ${MSDK_LIB}/PeriphDrivers/Source/TRNG
      )
  else()
    message(FATAL_ERROR "Unsupported MAX device: ${MAX_DEVICE}")
  endif()

  update_board(${BOARD_TARGET})

  target_compile_definitions(${BOARD_TARGET} PUBLIC
    BOARD_UF2_FAMILY_ID=${UF2_FAMILY_ID}
    TARGET=${MAX_DEVICE_UPPER}
    TARGET_REV=0x4131
    MXC_ASSERT_ENABLE
    ${MAX_DEVICE_UPPER}
    IAR_PRAGMAS=0
    FLASH_BOOT_SIZE=${FLASH_BOOT_SIZE}
    MAX_PERIPH_ID=${PERIPH_ID}
    )
  target_compile_options(${BOARD_TARGET} PUBLIC
    )
  target_link_options(${BOARD_TARGET} PUBLIC
    -nostartfiles
    --specs=nosys.specs --specs=nano.specs
    -Wl,--defsym=__FLASH_BOOT_SIZE=${FLASH_BOOT_SIZE}
    )
endfunction()
