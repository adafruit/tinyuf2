# The following five lines of boilerplate have to be in your project's
# CMakeLists in this exact order for cmake to work correctly
cmake_minimum_required(VERSION 3.17)

include(${CMAKE_CURRENT_LIST_DIR}/../../../family_support.cmake)

# Must be set before including IDF project.cmake
set(EXTRA_COMPONENT_DIRS "../../boards" "../../components")
set(SDKCONFIG ${CMAKE_BINARY_DIR}/sdkconfig)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)

add_compile_definitions(
  BUILD_APPLICATION
  BUILD_NO_TINYUSB
  )

project(blinky)

set(ARTIFACT_PATH ${CMAKE_CURRENT_LIST_DIR}/../../_bin/${BOARD})
cmake_print_variables(UF2_FAMILY_ID)
add_custom_command(TARGET app POST_BUILD
  COMMAND ${Python_EXECUTABLE} ${UF2CONV_PY} -f ${UF2_FAMILY_ID} -b 0x0 -c -o ${CMAKE_BINARY_DIR}/blinky.uf2 ${CMAKE_BINARY_DIR}/blinky.bin
  COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_BINARY_DIR}/blinky.uf2 ${ARTIFACT_PATH}/apps/blinky.uf2
  VERBATIM
  )
