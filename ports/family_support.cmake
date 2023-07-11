include_guard()

include(CMakePrintHelpers)
find_package(Python COMPONENTS Interpreter)

# TOP is path to root directory
set(TOP ${CMAKE_CURRENT_LIST_DIR}/..)

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

function(family_add_bin_hex TARGET)
  add_custom_command(TARGET ${TARGET} POST_BUILD
    COMMAND ${CMAKE_OBJCOPY} -Obinary $<TARGET_FILE:${TARGET}> $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.bin
    COMMAND ${CMAKE_OBJCOPY} -Oihex $<TARGET_FILE:${TARGET}> $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.hex
    VERBATIM)
endfunction()

function(family_add_uf2 TARGET FAMILY_ID)
  add_custom_command(TARGET ${TARGET} POST_BUILD
    COMMAND ${Python_EXECUTABLE} ${UF2CONV_PY} -f ${FAMILY_ID} -c -o $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.uf2
    $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.hex
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


# Add flash pycod target
function(family_flash_pyocd TARGET)
  if (NOT DEFINED PYOC)
    set(PYOCD pyocd)
  endif ()

  add_custom_target(${TARGET}-pyocd
    DEPENDS ${TARGET}
    COMMAND ${PYOCD} flash -t ${PYOCD_TARGET} $<TARGET_FILE:${TARGET}>
    )
endfunction()


# Add flash using NXP's LinkServer (redserver)
# https://www.nxp.com/design/software/development-software/mcuxpresso-software-and-tools-/linkserver-for-microcontrollers:LINKERSERVER
function(family_flash_nxplink TARGET)
  if (NOT DEFINED LINKSERVER)
    set(LINKSERVER LinkServer)
  endif ()

  # LinkServer has a bug that can only execute with full path otherwise it throws:
  # realpath error: No such file or directory
  execute_process(COMMAND which ${LINKSERVER} OUTPUT_VARIABLE LINKSERVER_PATH OUTPUT_STRIP_TRAILING_WHITESPACE)

  add_custom_target(${TARGET}-nxplink
    DEPENDS ${TARGET}
    COMMAND ${LINKSERVER_PATH} flash ${NXPLINK_DEVICE} load $<TARGET_FILE:${TARGET}>
    )
endfunction()


#----------------------------------
# Family specific
#----------------------------------

include(${CMAKE_CURRENT_LIST_DIR}/${FAMILY}/family.cmake)
