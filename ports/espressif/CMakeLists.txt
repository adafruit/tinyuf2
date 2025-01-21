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

# Post build: generate bootloader_bin.c for self-update and combined.bin
add_custom_command(TARGET app POST_BUILD
  COMMAND ${Python_EXECUTABLE} ${UF2CONV_PY} --carray -o ${CMAKE_CURRENT_LIST_DIR}/apps/self_update/main/bootloader_bin.c ${CMAKE_BINARY_DIR}/tinyuf2.bin
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

  add_custom_command(TARGET app POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_BINARY_DIR}/tinyuf2.bin ${ARDUINO_VARIANT_DIR}/tinyuf2.bin
    )
endif ()
