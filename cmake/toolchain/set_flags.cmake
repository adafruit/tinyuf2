include(CMakePrintHelpers)

# join the toolchain flags into a single string
list(JOIN TOOLCHAIN_COMMON_FLAGS " " TOOLCHAIN_COMMON_FLAGS)

foreach (LANG IN ITEMS C CXX ASM)
  set(CMAKE_${LANG}_FLAGS_INIT ${TOOLCHAIN_COMMON_FLAGS})
  #cmake_print_variables(CMAKE_${LANG}_FLAGS_INIT)
endforeach ()

# Linker
list(JOIN TOOLCHAIN_EXE_LINKER_FLAGS " " CMAKE_EXE_LINKER_FLAGS_INIT)
