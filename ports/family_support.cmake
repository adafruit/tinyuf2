include_guard(GLOBAL)

include(CMakePrintHelpers)
find_package(Python COMPONENTS Interpreter)
find_package(Git REQUIRED)

# TOP is path to root directory
set(TOP ${CMAKE_CURRENT_LIST_DIR}/..)
get_filename_component(TOP ${TOP} ABSOLUTE)

set(UF2CONV_PY ${TOP}/lib/uf2/utils/uf2conv.py)

#-------------------------------------------------------------
# Toolchain
# Can be changed via -DTOOLCHAIN=gcc|iar or -DCMAKE_C_COMPILER=
#-------------------------------------------------------------
# Detect toolchain based on CMAKE_C_COMPILER
if (DEFINED CMAKE_C_COMPILER)
  string(FIND ${CMAKE_C_COMPILER} "iccarm" IS_IAR)
  string(FIND ${CMAKE_C_COMPILER} "clang" IS_CLANG)
  string(FIND ${CMAKE_C_COMPILER} "gcc" IS_GCC)

  if (NOT IS_IAR EQUAL -1)
    set(TOOLCHAIN iar)
  elseif (NOT IS_CLANG EQUAL -1)
    set(TOOLCHAIN clang)
  elseif (NOT IS_GCC EQUAL -1)
    set(TOOLCHAIN gcc)
  endif ()
endif ()

if (NOT DEFINED TOOLCHAIN)
  set(TOOLCHAIN gcc)
endif ()

if (NOT DEFINED CMAKE_BUILD_TYPE OR CMAKE_BUILD_TYPE STREQUAL "")
  set(CMAKE_BUILD_TYPE MinSizeRel CACHE STRING "Build type" FORCE)
endif ()

#-------------------------------------------------------------
# FAMILY and BOARD
#-------------------------------------------------------------
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

set(FAMILY_PATH ${TOP}/ports/${FAMILY} CACHE INTERNAL "FAMILY_PATH")
set(BOARD_PATH ${TOP}/ports/${FAMILY}/boards/${BOARD} CACHE INTERNAL "BOARD_PATH")

set(ARTIFACT_PATH ${FAMILY_PATH}/_bin/${BOARD})
execute_process(COMMAND mkdir -p ${ARTIFACT_PATH})
execute_process(COMMAND mkdir -p ${ARTIFACT_PATH}/apps)

# enable LTO if supported
include(CheckIPOSupported)
check_ipo_supported(RESULT IPO_SUPPORTED)
if (IPO_SUPPORTED)
  set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)
endif ()

#------------------------------------
# Functions
#------------------------------------

# Generate bin/hex output, can be override by family specific
function(family_gen_bin_hex TARGET)
  add_custom_command(TARGET ${TARGET} POST_BUILD
    COMMAND ${CMAKE_OBJCOPY} -Obinary $<TARGET_FILE:${TARGET}> $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.bin
    COMMAND ${CMAKE_OBJCOPY} -Oihex $<TARGET_FILE:${TARGET}> $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.hex
    VERBATIM)
endfunction()

function(family_add_default_warnings TARGET)
  target_compile_options(${TARGET} PUBLIC
    -Wall
    -Wextra
    #-Werror
    -Wfatal-errors
    -Wdouble-promotion
    -Wstrict-prototypes
    -Wstrict-overflow
    -Werror-implicit-function-declaration
    -Wfloat-equal
    -Wundef
    -Wshadow
    -Wwrite-strings
    -Wsign-compare
    -Wmissing-format-attribute
    -Wunreachable-code
    -Wcast-align
    -Wcast-function-type
    -Wcast-qual
    -Wnull-dereference
    -Wuninitialized
    -Wunused
    -Wunused-function
    -Wreturn-type
    -Wredundant-decls
    -Wmissing-prototypes
    )

  if (CMAKE_C_COMPILER_ID STREQUAL "GNU")
    if (CMAKE_C_COMPILER_VERSION VERSION_GREATER_EQUAL 12.0)
      target_link_options(${TARGET} PUBLIC "LINKER:--no-warn-rwx-segments")
    endif ()
  endif ()
endfunction()

function(family_configure_common TARGET)
  # Add BOARD_${BOARD} define
  string(TOUPPER ${BOARD} BOARD_UPPER)
  string(REPLACE "-" "_" BOARD_UPPER ${BOARD_UPPER})
  target_compile_definitions(${TARGET} PUBLIC
    BOARD_${BOARD_UPPER}
  )

  # compile define from command line
  if(DEFINED CFLAGS_CLI)
    separate_arguments(CFLAGS_CLI)
    target_compile_options(${TARGET} PUBLIC ${CFLAGS_CLI})
  endif()

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
      target_sources(${TARGET} PUBLIC ${TOP}/lib/SEGGER_RTT/RTT/SEGGER_RTT.c)
      target_include_directories(${TARGET}  PUBLIC ${TOP}/lib/SEGGER_RTT/RTT)
#      target_compile_definitions(${TARGET}  PUBLIC SEGGER_RTT_MODE_DEFAULT=SEGGER_RTT_MODE_BLOCK_IF_FIFO_FULL)
    endif ()
  endif ()

  family_add_default_warnings(${TARGET})
  target_link_options(${TARGET} PUBLIC "LINKER:-Map=$<TARGET_FILE:${TARGET}>.map")

  # run size after build
  add_custom_command(TARGET ${TARGET} POST_BUILD
    COMMAND ${CMAKE_SIZE} $<TARGET_FILE:${TARGET}>
    )

  # add hex, bin and uf2 targets
  family_gen_bin_hex(${TARGET})
endfunction()

# Add tinyusb to example
function(family_add_tinyusb TARGET OPT_MCU)
  # tinyusb's CMakeList.txt
  add_subdirectory(${TOP}/lib/tinyusb/src ${CMAKE_CURRENT_BINARY_DIR}/tinyusb)

  # Add TinyUSB sources, include and common define
  tinyusb_target_add(${TARGET})
  target_compile_definitions(${TARGET} PUBLIC CFG_TUSB_MCU=${OPT_MCU})
  if (DEFINED LOG)
    target_compile_definitions(${TARGET} PUBLIC CFG_TUSB_DEBUG=${LOG})
    if (LOG STREQUAL "4") # no inline for debug level 4
      target_compile_definitions(${TARGET} PUBLIC TU_ATTR_ALWAYS_INLINE=)
    endif ()
  endif()
endfunction()

function(family_configure_tinyuf2 TARGET OPT_MCU)
  family_configure_common(${TARGET})

  include(${TOP}/src/tinyuf2.cmake)
  add_tinyuf2_src(${TARGET})

  family_add_tinyusb(${TARGET} ${OPT_MCU})

  # Add uf2 version
  execute_process(COMMAND ${GIT_EXECUTABLE} describe --dirty --always --tags OUTPUT_VARIABLE GIT_VERSION)
  string(STRIP ${GIT_VERSION} GIT_VERSION)
  cmake_print_variables(GIT_VERSION)
  target_compile_definitions(${TARGET} PUBLIC
    UF2_VERSION_BASE="${GIT_VERSION}"
    UF2_VERSION="${GIT_VERSION}"
    )

  # copy bin,hex to ARTIFACT_PATH
  add_custom_command(TARGET ${TARGET} POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.bin ${ARTIFACT_PATH}/${TARGET}.bin
    COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.hex ${ARTIFACT_PATH}/${TARGET}.hex
    VERBATIM)

endfunction()

# generate .uf2 file from hex
function(family_gen_uf2 TARGET FAMILY_ID)
  add_custom_command(TARGET ${TARGET} POST_BUILD
    COMMAND ${Python_EXECUTABLE} ${UF2CONV_PY} -f ${FAMILY_ID} -c -o $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.uf2 $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.hex
    COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.uf2 ${ARTIFACT_PATH}/apps/${TARGET}.uf2
    VERBATIM)
endfunction()

# generate .uf2 file from bin with address
function(family_gen_uf2_from_bin TARGET FAMILY_ID BIN_ADDR)
  add_custom_command(TARGET ${TARGET} POST_BUILD
    COMMAND ${Python_EXECUTABLE} ${UF2CONV_PY} -f ${FAMILY_ID} -b ${BIN_ADDR} -c -o $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.uf2 $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.bin
    VERBATIM)
endfunction()

#----------------------------------
# Flashing target
#----------------------------------

# Add flash jlink target, optional parameter is the extension of the binary file
function(family_flash_jlink TARGET)
  if (NOT DEFINED JLINKEXE)
    if(CMAKE_HOST_WIN32)
      set(JLINKEXE JLink.exe)
    else()
      set(JLINKEXE JLinkExe)
    endif()
  endif ()

  if (NOT DEFINED JLINK_IF)
    set(JLINK_IF swd)
  endif ()

  if (NOT DEFINED JLINK_OPTION)
    set(JLINK_OPTION "")
  endif ()
  separate_arguments(JLINK_OPTION UNIX_COMMAND ${JLINK_OPTION})

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
    COMMAND ${JLINKEXE} -device ${JLINK_DEVICE} ${JLINK_OPTION} -if ${JLINK_IF} -JTAGConf -1,-1 -speed auto -CommandFile ${CMAKE_CURRENT_BINARY_DIR}/${TARGET}.jlink
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

  if (DEFINED OPENOCD_SERIAL)
    set(OPENOCD_OPTION "-c \"adapter serial ${OPENOCD_SERIAL}\" ${OPENOCD_OPTION}")
  endif ()

  separate_arguments(OPTION_LIST UNIX_COMMAND ${OPENOCD_OPTION})
  separate_arguments(OPTION_LIST2 UNIX_COMMAND ${OPENOCD_OPTION2})

  # note skip verify since it has issue with rp2040
  add_custom_target(${TARGET}-openocd
    DEPENDS ${TARGET}
    COMMAND ${OPENOCD} -c "tcl_port disabled; gdb_port disabled" ${OPTION_LIST} -c "init; halt; program $<TARGET_FILE:${TARGET}>" -c reset ${OPTION_LIST2} -c exit
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


# Add flash openocd adi (Analog Devices) target
# included with msdk or compiled from release branch of https://github.com/analogdevicesinc/openocd
function(family_flash_openocd_adi TARGET)
  if (DEFINED MAXIM_PATH)
    # use openocd from msdk with MAXIM_PATH cmake variable first if the user
    # specified it
    set(OPENOCD ${MAXIM_PATH}/Tools/OpenOCD/openocd)
    set(OPENOCD_OPTION2 "-s ${MAXIM_PATH}/Tools/OpenOCD/scripts")
  elseif (DEFINED ENV{MAXIM_PATH})
    # use openocd from msdk with MAXIM_PATH environment variable. Normalize
    # since msdk can be Windows (MinGW) or Linux
    file(TO_CMAKE_PATH "$ENV{MAXIM_PATH}" MAXIM_PATH_NORM)
    set(OPENOCD ${MAXIM_PATH_NORM}/Tools/OpenOCD/openocd)
    set(OPENOCD_OPTION2 "-s ${MAXIM_PATH_NORM}/Tools/OpenOCD/scripts")
  else()
    # compiled from source
    if (NOT DEFINED OPENOCD_ADI_PATH)
      set(OPENOCD_ADI_PATH $ENV{HOME}/app/openocd_adi)
    endif ()
    set(OPENOCD ${OPENOCD_ADI_PATH}/src/openocd)
    set(OPENOCD_OPTION2 "-s ${OPENOCD_ADI_PATH}/tcl")
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
