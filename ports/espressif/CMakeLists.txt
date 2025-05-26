# The following five lines of boilerplate have to be in your project's
# CMakeLists in this exact order for cmake to work correctly
cmake_minimum_required(VERSION 3.17)

include(${CMAKE_CURRENT_LIST_DIR}/../family_support.cmake)

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
    "gen_esp32part.py ${CMAKE_CURRENT_LIST_DIR}/partitions-4MB.csv ${CMAKE_BINARY_DIR}/partition_table/partitions-table-ota.bin\n"
    "esptool.py --chip ${IDF_TARGET} merge_bin --output combined-ota.bin $(tr '\\n' ' ' < ${CMAKE_BINARY_DIR}/flash_args | sed 's/partition-table.bin/partitions-table-ota.bin/g')\n"
    "cp ${CMAKE_BINARY_DIR}/partition_table/partitions-table-ota.bin ${ARTIFACT_PATH}/partitions-table-ota.bin\n"
    "cp combined-ota.bin ${ARTIFACT_PATH}/combined-ota.bin\n"
    )
endif()

add_custom_command(TARGET app POST_BUILD
  COMMAND bash ${CMAKE_BINARY_DIR}/tinyuf2.postbuild.sh
  WORKING_DIRECTORY ${CMAKE_BINARY_DIR}
  VERBATIM
  )

# Post build: copy binaries for artifact
add_custom_command(TARGET app POST_BUILD
  COMMAND ${CMAKE_COMMAND} -E echo "Copy binaries for artifact"
  COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_BINARY_DIR}/flash_args ${ARTIFACT_PATH}/flash_args
  COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_BINARY_DIR}/bootloader/bootloader.bin ${ARTIFACT_PATH}/bootloader.bin
  COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_BINARY_DIR}/ota_data_initial.bin ${ARTIFACT_PATH}/ota_data_initial.bin
  COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_BINARY_DIR}/partition_table/partition-table.bin ${ARTIFACT_PATH}/partition-table.bin
  COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_BINARY_DIR}/tinyuf2.bin ${ARTIFACT_PATH}/tinyuf2.bin
  COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_BINARY_DIR}/combined.bin ${ARTIFACT_PATH}/combined.bin
  VERBATIM
  )

# flash combined.bin
add_custom_target(combined-flash
  DEPENDS tinyuf2.elf
  COMMAND ${CMAKE_COMMAND} -E echo "Flashing combined.bin"
  COMMAND esptool.py --chip ${IDF_TARGET} write_flash 0x0 combined.bin
  VERBATIM
  )

#------------------------------
# External project (update_tinyuf2, blinky etc ...)
#------------------------------

# Post build: generate bootloader_bin.c for update-tinyuf2 and combined.bin
add_custom_command(TARGET app POST_BUILD
  COMMAND ${Python_EXECUTABLE} ${UF2CONV_PY} --carray -o ${CMAKE_CURRENT_LIST_DIR}/apps/update_tinyuf2/main/bootloader_bin.c ${CMAKE_BINARY_DIR}/tinyuf2.bin
  )

externalproject_add(update-tinyuf2
  SOURCE_DIR ${CMAKE_CURRENT_LIST_DIR}/apps/update_tinyuf2
  BINARY_DIR ${CMAKE_BINARY_DIR}/apps/update_tinyuf2
  # Modifying the list separator for the arguments, as such, we won't need to manually
  # replace the new separator by the default ';' in the subproject
  CMAKE_ARGS -DBOARD=${BOARD}
  INSTALL_COMMAND ""
  BUILD_ALWAYS 1
  DEPENDS tinyuf2.elf
  )

externalproject_add(blinky
  SOURCE_DIR ${CMAKE_CURRENT_LIST_DIR}/apps/blinky
  BINARY_DIR ${CMAKE_BINARY_DIR}/apps/blinky
  # Modifying the list separator for the arguments, as such, we won't need to manually
  # replace the new separator by the default ';' in the subproject
  CMAKE_ARGS -DBOARD=${BOARD}
  INSTALL_COMMAND ""
  BUILD_ALWAYS 1
  )

# erase firmware need to use reset reason, not implemented yet
#externalproject_add(erase_firmware
#  SOURCE_DIR ${CMAKE_CURRENT_LIST_DIR}/apps/erase_firmware
#  BINARY_DIR ${CMAKE_BINARY_DIR}/apps/erase_firmware
#  # Modifying the list separator for the arguments, as such, we won't need to manually
#  # replace the new separator by the default ';' in the subproject
#  CMAKE_ARGS -DBOARD=${BOARD}
#  INSTALL_COMMAND ""
#  BUILD_ALWAYS 1
#  )

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
