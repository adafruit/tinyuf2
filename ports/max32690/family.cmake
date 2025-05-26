include_guard(GLOBAL)

#------------------------------------
# Config
#------------------------------------

set(UF2_FAMILY_ID 0x7410520a)
set(MAX32_LIB ${TOP}/lib/mcu/analog/max32/Libraries)

include(${CMAKE_CURRENT_LIST_DIR}/boards/${BOARD}/board.cmake)

# enable LTO
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)

set(CMAKE_SYSTEM_PROCESSOR cortex-m4 CACHE INTERNAL "System Processor")
set(CMAKE_TOOLCHAIN_FILE ${TOP}/cmake/toolchain/arm_${TOOLCHAIN}.cmake)

string(TOUPPER ${MAX_DEVICE} MAX_DEVICE_UPPER)

# 32KB
set(FLASH_BOOT_SIZE 0x8000)

#------------------------------------
# BOARD_TARGET
#------------------------------------
function(family_add_board_target BOARD_TARGET)
  if (TARGET ${BOARD_TARGET})
    return()
  endif ()

  add_library(${BOARD_TARGET} STATIC
    ${MAX32_LIB}/CMSIS/Device/Maxim/MAX32690/Source/GCC/startup_max32690.S
    ${MAX32_LIB}/CMSIS/Device/Maxim/MAX32690/Source/heap.c
    ${MAX32_LIB}/CMSIS/Device/Maxim/MAX32690/Source/system_max32690.c
    ${MAX32_LIB}/PeriphDrivers/Source/SYS/mxc_assert.c
    ${MAX32_LIB}/PeriphDrivers/Source/SYS/mxc_delay.c
    ${MAX32_LIB}/PeriphDrivers/Source/SYS/mxc_lock.c
    ${MAX32_LIB}/PeriphDrivers/Source/SYS/nvic_table.c
    ${MAX32_LIB}/PeriphDrivers/Source/SYS/pins_me18.c
    ${MAX32_LIB}/PeriphDrivers/Source/SYS/sys_me18.c
    ${MAX32_LIB}/PeriphDrivers/Source/CTB/ctb_me18.c
    ${MAX32_LIB}/PeriphDrivers/Source/CTB/ctb_reva.c
    ${MAX32_LIB}/PeriphDrivers/Source/CTB/ctb_common.c
    ${MAX32_LIB}/PeriphDrivers/Source/FLC/flc_common.c
    ${MAX32_LIB}/PeriphDrivers/Source/FLC/flc_me18.c
    ${MAX32_LIB}/PeriphDrivers/Source/FLC/flc_reva.c
    ${MAX32_LIB}/PeriphDrivers/Source/GPIO/gpio_common.c
    ${MAX32_LIB}/PeriphDrivers/Source/GPIO/gpio_me18.c
    ${MAX32_LIB}/PeriphDrivers/Source/GPIO/gpio_reva.c
    ${MAX32_LIB}/PeriphDrivers/Source/ICC/icc_me18.c
    ${MAX32_LIB}/PeriphDrivers/Source/ICC/icc_reva.c
    ${MAX32_LIB}/PeriphDrivers/Source/UART/uart_common.c
    ${MAX32_LIB}/PeriphDrivers/Source/UART/uart_me18.c
    ${MAX32_LIB}/PeriphDrivers/Source/UART/uart_revb.c
    )
  target_include_directories(${BOARD_TARGET} PUBLIC
    # port & board
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/boards/${BOARD}
    # sdk
    ${MAX32_LIB}/CMSIS/5.9.0/Core/Include
    ${MAX32_LIB}/CMSIS/Device/Maxim/MAX32690/Include
    ${MAX32_LIB}/PeriphDrivers/Include/MAX32690
    ${MAX32_LIB}/PeriphDrivers/Source/SYS
    ${MAX32_LIB}/PeriphDrivers/Source/GPIO
    ${MAX32_LIB}/PeriphDrivers/Source/CTB
    ${MAX32_LIB}/PeriphDrivers/Source/ICC
    ${MAX32_LIB}/PeriphDrivers/Source/FLC
    ${MAX32_LIB}/PeriphDrivers/Source/UART
    )

  update_board(${BOARD_TARGET})

  target_compile_definitions(${BOARD_TARGET} PUBLIC
    BOARD_UF2_FAMILY_ID=${UF2_FAMILY_ID}
    TARGET=MAX32690
    TARGET_REV=0x4131
    MXC_ASSERT_ENABLE
    MAX32690
    IAR_PRAGMAS=0
    FLASH_BOOT_SIZE=${FLASH_BOOT_SIZE}
    )
  target_compile_options(${BOARD_TARGET} PUBLIC
    )
  target_link_options(${BOARD_TARGET} PUBLIC
    -nostartfiles
    --specs=nosys.specs --specs=nano.specs
    -Wl,--defsym=__FLASH_BOOT_SIZE=${FLASH_BOOT_SIZE}
    )
endfunction()

#------------------------------------
# Main target
#------------------------------------
