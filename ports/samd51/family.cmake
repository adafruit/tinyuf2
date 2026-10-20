include_guard(GLOBAL)

#------------------------------------
# Config
#------------------------------------

set(UF2_FAMILY_ID 0x55114460)
set(SAM_SDK ${TOP}/lib/mcu/microchip/samd51)
set(CMSIS_5 ${TOP}/lib/CMSIS_5)

include(${CMAKE_CURRENT_LIST_DIR}/boards/${BOARD}/board.cmake)

# the bootloader area is write protected: lift BOOTPROT before programming, the bootloader protects itself again at boot
set(OPENOCD_OPTION "-f interface/cmsis-dap.cfg -c \"transport select swd\" -c \"set CHIPNAME at91samd51n20a\" -f target/atsame5x.cfg -c \"adapter speed 4000\" -c init -c \"reset halt\" -c \"atsame5 bootloader 0\" -c \"reset halt\"")

# increase flash size if debug build
if (CMAKE_BUILD_TYPE STREQUAL "Debug")
  set(LD_FLASH_BOOT_SIZE 64K)
endif ()

# enable LTO
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)

set(CMAKE_SYSTEM_PROCESSOR cortex-m4 CACHE INTERNAL "System Processor")
set(CMAKE_TOOLCHAIN_FILE ${TOP}/cmake/toolchain/arm_${TOOLCHAIN}.cmake)

#------------------------------------
# BOARD_TARGET
#------------------------------------
function(family_add_board_target BOARD_TARGET)
  if (TARGET ${BOARD_TARGET})
    return()
  endif ()

  add_library(${BOARD_TARGET} STATIC
    ${SAM_SDK}/gcc/system_samd51.c
    ${SAM_SDK}/gcc/gcc/startup_samd51.c
    )
  target_include_directories(${BOARD_TARGET} PUBLIC
    # port & board
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/boards/${BOARD}
    # sdk
    ${CMSIS_5}/CMSIS/Core/Include
    ${SAM_SDK}/include
    )

  update_board(${BOARD_TARGET})

  target_compile_definitions(${BOARD_TARGET} PUBLIC
    BOARD_UF2_FAMILY_ID=${UF2_FAMILY_ID}
    )
  set_source_files_properties(${SAM_SDK}/gcc/system_samd51.c ${SAM_SDK}/gcc/gcc/startup_samd51.c PROPERTIES
    COMPILE_OPTIONS -w)
  target_link_options(${BOARD_TARGET} PUBLIC
    -nostartfiles
    --specs=nosys.specs --specs=nano.specs
    -Wl,--defsym=__flash_boot_size=${LD_FLASH_BOOT_SIZE}
    -Wl,--defsym=__flash_size=${LD_FLASH_SIZE}
    -Wl,--defsym=__ram_size=${LD_RAM_SIZE}
    )
endfunction()
