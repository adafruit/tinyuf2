# The following five lines of boilerplate have to be in your project's
# CMakeLists in this exact order for cmake to work correctly
cmake_minimum_required(VERSION 3.17)

include(${CMAKE_CURRENT_LIST_DIR}/../family_support.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/boards/${BOARD}/board.cmake)

# Must be set before including IDF project.cmake
set(EXTRA_COMPONENT_DIRS ${TOP}/src ${CMAKE_CURRENT_LIST_DIR}/boards)
set(SDKCONFIG_DEFAULTS ${CMAKE_CURRENT_LIST_DIR}/sdkconfig.defaults ${CMAKE_CURRENT_LIST_DIR}/boards/${BOARD}/sdkconfig)
set(SDKCONFIG ${CMAKE_BINARY_DIR}/sdkconfig)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
idf_build_set_property(EXTRA_CMAKE_ARGS -DBOARD=${BOARD}) # Pass BOARD to bootloader

execute_process(COMMAND git describe --dirty --always --tags
                OUTPUT_VARIABLE GIT_VERSION)
string(STRIP ${GIT_VERSION} GIT_VERSION)

execute_process(COMMAND bash "-c" "git submodule status ${TOP}/lib/tinyusb | cut -d\" \" -f3,4 | paste -s -d\" \" -"
                OUTPUT_VARIABLE GIT_SUBMODULE_VERSIONS)

string(REPLACE ../ "" GIT_SUBMODULE_VERSIONS ${GIT_SUBMODULE_VERSIONS})
string(REPLACE lib/ "" GIT_SUBMODULE_VERSIONS ${GIT_SUBMODULE_VERSIONS})
string(STRIP ${GIT_SUBMODULE_VERSIONS} GIT_SUBMODULE_VERSIONS)

add_compile_definitions(
  UF2_VERSION_BASE="${GIT_VERSION}"
  UF2_VERSION="${GIT_VERSION} - ${GIT_SUBMODULE_VERSIONS}"
  )
cmake_print_variables(GIT_VERSION GIT_SUBMODULE_VERSIONS)

project(tinyuf2)

set(ARTIFACT_PATH ${CMAKE_CURRENT_LIST_DIR}/_bin/${BOARD})
execute_process(COMMAND mkdir -p ${ARTIFACT_PATH})

# Create post-build script for combined.bin / combined-ota.bin
file(WRITE ${CMAKE_BINARY_DIR}/tinyuf2.postbuild.sh
  "#!/bin/bash\n"
  "echo \"Creating combined.bin\"\n"
  "esptool.py --chip ${IDF_TARGET} merge_bin --output combined.bin $(tr '\\n' ' ' < ${CMAKE_BINARY_DIR}/flash_args)\n"
)

# check if board is 4MB flash and create combined-ota.bin
file(READ ${CMAKE_CURRENT_LIST_DIR}/boards/${BOARD}/sdkconfig BOARD_SDKCONFIG_CONTENTS)
string(FIND ${BOARD_SDKCONFIG_CONTENTS} "partitions-4MB-noota.csv" MATCH_INDEX)
if(NOT MATCH_INDEX EQUAL -1)
  file(APPEND ${CMAKE_BINARY_DIR}/tinyuf2.postbuild.sh
    "echo \"Creating combined-ota.bin\"\n"
    "gen_esp32part.py ${CMAKE_CURRENT_LIST_DIR}/partitions-4MB.csv ${CMAKE_BINARY_DIR}/partition_table/partitions-table-4MB-ota.bin\n"
    "esptool.py --chip ${IDF_TARGET} merge_bin --output combined_ota.bin $(tr '\\n' ' ' < ${CMAKE_BINARY_DIR}/flash_args | sed 's/partition-table.bin/partitions-table-4MB-ota.bin/g')\n"
    "cp combined_ota.bin ${ARTIFACT_PATH}/combined_ota.bin\n"
    )
endif()

add_custom_command(TARGET app POST_BUILD
  COMMAND bash ${CMAKE_BINARY_DIR}/tinyuf2.postbuild.sh
  VERBATIM
  )

# Post build: copy binaries for artifact
add_custom_command(TARGET app POST_BUILD
  COMMAND ${CMAKE_COMMAND} -E echo "Copy binaries for artifact"
  COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_BINARY_DIR}/bootloader/bootloader.bin ${ARTIFACT_PATH}/bootloader.bin
  COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_BINARY_DIR}/ota_data_initial.bin ${ARTIFACT_PATH}/ota_data_initial.bin
  COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_BINARY_DIR}/partition_table/partition-table.bin ${ARTIFACT_PATH}/partition-table.bin
  COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_BINARY_DIR}/tinyuf2.bin ${ARTIFACT_PATH}/tinyuf2.bin
  COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_BINARY_DIR}/combined.bin ${ARTIFACT_PATH}/combined.bin
  VERBATIM
  )

# External project for self-update
# Post build: generate bootloader_bin.c for self-update and combined.bin
add_custom_command(TARGET app POST_BUILD
  COMMAND ${Python_EXECUTABLE} ${UF2CONV_PY} --carray -o ${CMAKE_CURRENT_LIST_DIR}/apps/self_update/main/bootloader_bin.c ${CMAKE_BINARY_DIR}/tinyuf2.bin
  )

externalproject_add(self_update
  SOURCE_DIR ${CMAKE_CURRENT_LIST_DIR}/apps/self_update
  BINARY_DIR ${CMAKE_BINARY_DIR}/self_update
  # Modifying the list separator for the arguments, as such, we won't need to manually
  # replace the new separator by the default ';' in the subproject
  CMAKE_ARGS -DBOARD=${BOARD}
  INSTALL_COMMAND ""
  BUILD_ALWAYS 1
  DEPENDS tinyuf2.elf
  )

# flash combined.bin
add_custom_target(combined-flash
  DEPENDS tinyuf2.elf
  COMMAND ${CMAKE_COMMAND} -E echo "Flashing combined.bin"
  COMMAND esptool.py --chip ${IDF_TARGET} write_flash 0x0 combined.bin
  VERBATIM
  )

# -------------------------------------------------------------
# Post build: update arduino-esp32 bootloader for debug purpose
# -------------------------------------------------------------
if (0)
  set(ARDUINO_VARIANT_DIR $ENV{HOME}/code/arduino-esp32/variants/${BOARD})
  #set(ARDUINO_VARIANT_DIR $ENV{HOME}/code/arduino-esp32/variants/adafruit_feather_esp32s3_nopsram)

  add_custom_command(TARGET bootloader POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_BINARY_DIR}/bootloader/bootloader.bin ${ARDUINO_VARIANT_DIR}/bootloader-tinyuf2.bin
    )

  add_custom_command(TARGET tinyuf2.elf POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_BINARY_DIR}/tinyuf2.bin ${ARDUINO_VARIANT_DIR}/tinyuf2.bin
    )
endif ()
