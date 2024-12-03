include_guard()

include(CMakePrintHelpers)
find_package(Python COMPONENTS Interpreter)
find_package(Git REQUIRED)

# TOP is path to root directory
set(TOP ${CMAKE_CURRENT_LIST_DIR}/..)
#get_filename_component(TOP "${TOP}" REALPATH)

# Default to gcc
if (NOT DEFINED TOOLCHAIN)
  set(TOOLCHAIN gcc)
endif ()

if (NOT BOARD)
  message(FATAL_ERROR "BOARD not specified")
endif ()

# FAMILY not defined, try to detect it from BOARD
if (NOT DEFINED FAMILY)
  # Find path contains BOARD
  file(GLOB BOARD_PATH LIST_DIRECTORIES true
    RELATIVE ${TOP}/ports
    ${TOP}/ports/*/boards/${BOARD}
    )
  if (NOT BOARD_PATH)
    message(FATAL_ERROR "Could not detect FAMILY from BOARD=${BOARD}")
  endif ()

  # replace / with ; so that we can get the first element as FAMILY
  string(REPLACE "/" ";" BOARD_PATH ${BOARD_PATH})
  list(GET BOARD_PATH 0 FAMILY)
endif ()

set(UF2CONV_PY ${TOP}/lib/uf2/utils/uf2conv.py)

# enable LTO if supported
include(CheckIPOSupported)
check_ipo_supported(RESULT IPO_SUPPORTED)
if (IPO_SUPPORTED)
  set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)
endif ()

#------------------------------------
# Functions
#------------------------------------

function(family_add_bin_hex TARGET)
  # placeholder, will be override by family specific
endfunction()

function(family_add_default_example_warnings TARGET)
#  target_compile_options(${TARGET} PUBLIC
#    -Wall
#    -Wextra
#    -Werror
#    -Wfatal-errors
#    -Wdouble-promotion
#    -Wfloat-equal
#    -Wshadow
#    -Wwrite-strings
#    -Wsign-compare
#    -Wmissing-format-attribute
#    -Wunreachable-code
#    -Wcast-align
#    -Wcast-qual
#    -Wnull-dereference
#    -Wuninitialized
#    -Wunused
#    -Wredundant-decls
#    #-Wstrict-prototypes
#    #-Werror-implicit-function-declaration
#    #-Wundef
#    )

  if (CMAKE_C_COMPILER_ID STREQUAL "GNU")
    if (CMAKE_C_COMPILER_VERSION VERSION_GREATER_EQUAL 12.0)
      target_link_options(${TARGET} PUBLIC "LINKER:--no-warn-rwx-segments")
    endif ()

    # GCC 10
    if (CMAKE_C_COMPILER_VERSION VERSION_GREATER_EQUAL 10.0)
      target_compile_options(${TARGET} PUBLIC -Wconversion)
    endif ()

    # GCC 8
    if (CMAKE_C_COMPILER_VERSION VERSION_GREATER_EQUAL 8.0)
      target_compile_options(${TARGET} PUBLIC -Wcast-function-type -Wstrict-overflow)
    endif ()

    # GCC 6
    if (CMAKE_C_COMPILER_VERSION VERSION_GREATER_EQUAL 6.0)
      target_compile_options(${TARGET} PUBLIC -Wno-strict-aliasing)
    endif ()
  endif ()
endfunction()


function(family_configure_common TARGET)
  # run size after build
  add_custom_command(TARGET ${TARGET} POST_BUILD
    COMMAND ${CMAKE_SIZE} $<TARGET_FILE:${TARGET}>
    )

  # add hex, bin and uf2 targets
  family_add_bin_hex(${TARGET})

  # Add warnings flags

  # Generate map file
  target_link_options(${TARGET} PUBLIC "LINKER:-Map=$<TARGET_FILE:${TARGET}>.map")
  #family_add_linkermap(${TARGET})

  # executable target linked with board target
  family_add_board_target(board_${BOARD})
  target_link_libraries(${TARGET} PUBLIC board_${BOARD})

  # ETM Trace option
  if (TRACE_ETM STREQUAL "1")
    target_compile_definitions(${TARGET} PUBLIC TRACE_ETM)
  endif ()

  # LOGGER option
  if (DEFINED LOGGER)
    target_compile_definitions(${TARGET} PUBLIC LOGGER_${LOGGER})

    # Add segger rtt to example
    if(LOGGER STREQUAL "RTT" OR LOGGER STREQUAL "rtt")
      if (NOT TARGET segger_rtt)
        add_library(segger_rtt STATIC ${TOP}/lib/SEGGER_RTT/RTT/SEGGER_RTT.c)
        target_include_directories(segger_rtt PUBLIC ${TOP}/lib/SEGGER_RTT/RTT)
      endif()
      target_link_libraries(${TARGET} PUBLIC segger_rtt)
    endif ()
  endif ()
endfunction()


# Add tinyusb to example
function(family_add_tinyusb TARGET OPT_MCU RTOS)
  # tinyusb target is built for each example since it depends on example's tusb_config.h
  set(TINYUSB_TARGET_PREFIX ${TARGET}-)
  add_library(${TARGET}-tinyusb_config INTERFACE)

  # path to tusb_config.h
  target_include_directories(${TARGET}-tinyusb_config INTERFACE ${CMAKE_CURRENT_SOURCE_DIR})
  target_compile_definitions(${TARGET}-tinyusb_config INTERFACE CFG_TUSB_MCU=${OPT_MCU})

  if (DEFINED LOG)
    target_compile_definitions(${TARGET}-tinyusb_config INTERFACE CFG_TUSB_DEBUG=${LOG})
    if (LOG STREQUAL "4")
      # no inline for debug level 4
      target_compile_definitions(${TARGET}-tinyusb_config INTERFACE TU_ATTR_ALWAYS_INLINE=)
    endif ()
  endif()

  if (RTOS STREQUAL "freertos")
    target_compile_definitions(${TARGET}-tinyusb_config INTERFACE CFG_TUSB_OS=OPT_OS_FREERTOS)
  endif ()

  # tinyusb's CMakeList.txt
  add_subdirectory(${TOP}/lib/tinyusb/src ${CMAKE_CURRENT_BINARY_DIR}/tinyusb)

  if (RTOS STREQUAL "freertos")
    target_link_libraries(${TARGET}-tinyusb PUBLIC freertos_kernel)
  endif ()

  # tinyusb depends on board target for low level mcu header and function
  target_link_libraries(${TARGET}-tinyusb PUBLIC board_${BOARD})
  target_link_libraries(${TARGET} PUBLIC ${TARGET}-tinyusb)
endfunction()

function(family_add_uf2version TARGET DEPS_REPO)
  execute_process(COMMAND ${GIT_EXECUTABLE} describe --dirty --always --tags OUTPUT_VARIABLE GIT_VERSION)
  string(STRIP ${GIT_VERSION} GIT_VERSION)
#  string(REPLACE ${TOP}/ "" DEPS_REPO "${DEPS_REPO}")
#  foreach (DEP ${DEPS_REPO})
#    execute_process(COMMAND ${GIT_EXECUTABLE} -C ${TOP} submodule status ${DEP}
#      OUTPUT_VARIABLE DEP_VERSION
#      )
#    string(STRIP ${DEP_VERSION} DEP_VERSION)
#    string(FIND "${DEP_VERSION}" " " SPACE_POS)
#    string(SUBSTRING "${DEP_VERSION}" ${SPACE_POS} -1 DEP_VERSION)
#    string(STRIP ${DEP_VERSION} DEP_VERSION)
#
#    set(GIT_SUBMODULE_VERSIONS "${GIT_SUBMODULE_VERSIONS} ${DEP_VERSION}")
#  endforeach ()
#
#  string(STRIP ${GIT_SUBMODULE_VERSIONS} GIT_SUBMODULE_VERSIONS)
#  string(REPLACE lib/ "" GIT_SUBMODULE_VERSIONS ${GIT_SUBMODULE_VERSIONS})

  cmake_print_variables(GIT_VERSION)
  cmake_print_variables(GIT_SUBMODULE_VERSIONS)

  target_compile_definitions(${TARGET} PUBLIC
    UF2_VERSION_BASE="${GIT_VERSION}"
    UF2_VERSION="${GIT_VERSION} - ${GIT_SUBMODULE_VERSIONS}"
    )
endfunction()

function(family_configure_tinyuf2 TARGET OPT_MCU)
  family_configure_common(${TARGET})

  include(${TOP}/src/tinyuf2.cmake)
  add_tinyuf2(${TARGET})

  family_add_uf2version(${TARGET} "${FAMILY_SUBMODULE_DEPS}")
  family_add_tinyusb(${TARGET} ${OPT_MCU} none)
endfunction()


# Add bin/hex output
function(family_add_bin_hex TARGET)
  add_custom_command(TARGET ${TARGET} POST_BUILD
    COMMAND ${CMAKE_OBJCOPY} -Obinary $<TARGET_FILE:${TARGET}> $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.bin
    COMMAND ${CMAKE_OBJCOPY} -Oihex $<TARGET_FILE:${TARGET}> $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.hex
    VERBATIM)
endfunction()


# Add uf2 target, optional parameter is the extension of the binary file (default is hex)
# If bin file is used, address is also required
function(family_add_uf2 TARGET FAMILY_ID)
  set(BIN_EXT hex)
  set(ADDR_OPT "")
  if (ARGC GREATER 2)
    set(BIN_EXT ${ARGV2})
    if (BIN_EXT STREQUAL bin)
      set(ADDR_OPT "-b ${ARGV3}")
    endif ()
  endif ()

  set(BIN_FILE $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.${BIN_EXT})

  add_custom_command(TARGET ${TARGET} POST_BUILD
    COMMAND echo ${Python_EXECUTABLE} ${UF2CONV_PY} -f ${FAMILY_ID} ${ADDR_OPT} -c -o $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.uf2 ${BIN_FILE}
    COMMAND ${Python_EXECUTABLE} ${UF2CONV_PY} -f ${FAMILY_ID} ${ADDR_OPT} -c -o $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.uf2 ${BIN_FILE}
    VERBATIM)
endfunction()

function(family_add_linkermap TARGET)
  add_custom_command(TARGET ${TARGET} POST_BUILD
    COMMAND linkermap -v $<TARGET_FILE:${TARGET}>.map
    VERBATIM)
endfunction()

#----------------------------------
# Flashing target
#----------------------------------

# Add flash jlink target, optional parameter is the extension of the binary file
function(family_flash_jlink TARGET)
  if (NOT DEFINED JLINKEXE)
    set(JLINKEXE JLinkExe)
  endif ()

  if (NOT DEFINED JLINK_IF)
    set(JLINK_IF swd)
  endif ()

  if (ARGC GREATER 1)
    set(BIN_FILE $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.${ARGV1})
  else ()
    set(BIN_FILE $<TARGET_FILE:${TARGET}>)
  endif ()

  # flash with jlink
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
    COMMAND ${JLINKEXE} -device ${JLINK_DEVICE} -if ${JLINK_IF} -JTAGConf -1,-1 -speed auto -CommandFile ${CMAKE_CURRENT_BINARY_DIR}/${TARGET}.jlink
    )

  # erase with jlink
  file(GENERATE
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/${TARGET}-erase.jlink
    CONTENT "halt
erase
exit
  ")
  add_custom_target(${TARGET}-erase-jlink
    COMMAND ${JLINKEXE} -device ${JLINK_DEVICE} -if ${JLINK_IF} -JTAGConf -1,-1 -speed auto -CommandFile ${CMAKE_CURRENT_BINARY_DIR}/${TARGET}-erase.jlink
    )
endfunction()


# Add flash stlink target
function(family_flash_stlink TARGET)
  if (NOT DEFINED STM32_PROGRAMMER_CLI)
    set(STM32_PROGRAMMER_CLI STM32_Programmer_CLI)
  endif ()

  add_custom_target(${TARGET}-stlink
    DEPENDS ${TARGET}
    COMMAND ${STM32_PROGRAMMER_CLI} --connect port=swd --write $<TARGET_FILE:${TARGET}> --go
    )
endfunction()


# Add flash openocd target
function(family_flash_openocd TARGET)
  if (NOT DEFINED OPENOCD)
    set(OPENOCD openocd)
  endif ()

  if (NOT DEFINED OPENOCD_OPTION2)
    set(OPENOCD_OPTION2 "")
  endif ()

  separate_arguments(OPTION_LIST UNIX_COMMAND ${OPENOCD_OPTION})
  separate_arguments(OPTION_LIST2 UNIX_COMMAND ${OPENOCD_OPTION2})

  # note skip verify since it has issue with rp2040
  add_custom_target(${TARGET}-openocd
    DEPENDS ${TARGET}
    COMMAND ${OPENOCD} ${OPTION_LIST} -c "program $<TARGET_FILE:${TARGET}> reset" ${OPTION_LIST2} -c exit
    VERBATIM
    )
endfunction()

# Add flash openocd-wch target
# compiled from https://github.com/hathach/riscv-openocd-wch or https://github.com/dragonlock2/miscboards/blob/main/wch/SDK/riscv-openocd.tar.xz
function(family_flash_openocd_wch TARGET)
  if (NOT DEFINED OPENOCD)
    set(OPENOCD $ENV{HOME}/app/riscv-openocd-wch/src/openocd)
  endif ()

  family_flash_openocd(${TARGET})
endfunction()


# Flash with UF2
function(family_flash_uf2 TARGET FAMILY_ID)
  add_custom_target(${TARGET}-uf2
    DEPENDS ${TARGET}
    COMMAND ${Python_EXECUTABLE} ${UF2CONV_PY} -f ${FAMILY_ID} --deploy $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.uf2
    )
endfunction()

# Family specific
include(${CMAKE_CURRENT_LIST_DIR}/${FAMILY}/family.cmake)

# Family submodules dependencies
if (DEFINED FAMILY_SUBMODULE_DEPS)
  foreach(DEP ${FAMILY_SUBMODULE_DEPS})
    # Check if the submodule is present. If not, fetch it
    if(NOT EXISTS ${DEP}/.git)
      string(REPLACE ${TOP}/ "" DEP_REL ${DEP})
      execute_process(
        COMMAND ${GIT_EXECUTABLE} -C ${TOP} submodule update --init ${DEP_REL}
        )
    endif()
  endforeach()
endif ()
