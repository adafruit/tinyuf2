set(CMAKE_SYSTEM_NAME Generic)

set(CMAKE_ASM_COMPILER "arm-none-eabi-gcc")
set(CMAKE_C_COMPILER "arm-none-eabi-gcc")
set(CMAKE_CXX_COMPILER "arm-none-eabi-g++")

set(TOOLCHAIN_SIZE "arm-none-eabi-size" CACHE INTERNAL "")
set(GCC_ELF2BIN "arm-none-eabi-objcopy")
set_property(GLOBAL PROPERTY ELF2BIN ${GCC_ELF2BIN})

# Look for includes and libraries only in the target system prefix.
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)

# pass TOOLCHAIN_CPU to
set(CMAKE_TRY_COMPILE_PLATFORM_VARIABLES CMAKE_SYSTEM_PROCESSOR)

include(${CMAKE_CURRENT_LIST_DIR}/../cpu/${CMAKE_SYSTEM_PROCESSOR}.cmake)

# enable all possible warnings for building examples
list(APPEND TOOLCHAIN_COMMON_FLAGS
  -fdata-sections
  -ffunction-sections
  -fsingle-precision-constant
  -fno-strict-aliasing
  )

list(APPEND TOOLCHAIN_EXE_LINKER_FLAGS
  -fshort-enums
  -Wl,--print-memory-usage
  -Wl,--gc-sections
  -Wl,--cref
  )

include(${CMAKE_CURRENT_LIST_DIR}/set_flags.cmake)
