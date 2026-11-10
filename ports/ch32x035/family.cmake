include_guard(GLOBAL)

set(UF2_FAMILY_ID 0x699b62ec)
set(CH32_FAMILY ch32x035)
set(SDK_DIR ${TOP}/lib/mcu/wch/${CH32_FAMILY})
set(SDK_SRC_DIR ${SDK_DIR}/EVT/EXAM/SRC)

include(${CMAKE_CURRENT_LIST_DIR}/boards/${BOARD}/board.cmake)

# enable LTO
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)

set(CMAKE_SYSTEM_PROCESSOR rv32imac-ilp32 CACHE INTERNAL "System Processor")
set(CMAKE_TOOLCHAIN_FILE ${TOP}/cmake/toolchain/riscv_${TOOLCHAIN}.cmake)

set(OPENOCD_OPTION "-f ${CMAKE_CURRENT_LIST_DIR}/wch-riscv.cfg")

#------------------------------------
# BOARD_TARGET
#------------------------------------
# used by all executable targets

function(family_add_board_target BOARD_TARGET)
  if (TARGET ${BOARD_TARGET})
    return()
  endif ()

  set(STARTUP_FILE_GNU ${SDK_SRC_DIR}/Startup/startup_${CH32_FAMILY}.S)
  set(STARTUP_FILE_Clang ${STARTUP_FILE_GNU})

  add_library(${BOARD_TARGET} STATIC
    ${SDK_SRC_DIR}/Core/core_riscv.c
    ${SDK_SRC_DIR}/Peripheral/src/${CH32_FAMILY}_flash.c
    ${SDK_SRC_DIR}/Peripheral/src/${CH32_FAMILY}_gpio.c
    ${SDK_SRC_DIR}/Peripheral/src/${CH32_FAMILY}_misc.c
    ${SDK_SRC_DIR}/Peripheral/src/${CH32_FAMILY}_rcc.c
    ${SDK_SRC_DIR}/Peripheral/src/${CH32_FAMILY}_usart.c
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/system_${CH32_FAMILY}.c
    ${STARTUP_FILE_${CMAKE_C_COMPILER_ID}}
    )
  target_include_directories(${BOARD_TARGET} PUBLIC
    ${SDK_SRC_DIR}/Core
    ${SDK_SRC_DIR}/Peripheral/inc
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/boards/${BOARD}
    )

  # the on-chip USBFS IP (same driver path as CH58x)
  target_compile_definitions(${BOARD_TARGET} PUBLIC
    CFG_TUD_WCH_USBIP_USBFS=1
    )

  update_board(${BOARD_TARGET})

  target_compile_definitions(${BOARD_TARGET} PUBLIC
    BOARD_UF2_FAMILY_ID=${UF2_FAMILY_ID}
    )
  target_compile_options(${BOARD_TARGET} PUBLIC
    -mcmodel=medany
    -march=rv32imac_zicsr_zifencei
    -mabi=ilp32
    )
  # bootloader region size; LOG builds need more, e.g. -DBOOT_SIZE=28K (app must match)
  if (NOT DEFINED BOOT_SIZE)
    set(BOOT_SIZE 16K)
  endif ()
  target_link_options(${BOARD_TARGET} PUBLIC
    -march=rv32imac_zicsr_zifencei
    -mabi=ilp32
    -Wl,--defsym=__flash_size=${LD_FLASH_SIZE}
    -Wl,--defsym=__ram_size=${LD_RAM_SIZE}
    -Wl,--defsym=__boot_size=${BOOT_SIZE}
    -nostartfiles
    --specs=nosys.specs --specs=nano.specs
    )
endfunction()
