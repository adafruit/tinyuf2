# The following five lines of boilerplate have to be in your project's
# CMakeLists in this exact order for cmake to work correctly
cmake_minimum_required(VERSION 3.17)

include(${CMAKE_CURRENT_LIST_DIR}/../../../family_support.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/../../boards/${BOARD}/board.cmake)

# Must be set before including IDF project.cmake
set(EXTRA_COMPONENT_DIRS "../../boards" "../../components")
set(SDKCONFIG ${CMAKE_BINARY_DIR}/sdkconfig)

set(SELFUPDATE_BUILD 1)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

add_compile_definitions(TINYUF2_SELF_UPDATE)

project(update-tinyuf2)

set(ARTIFACT_PATH ${CMAKE_CURRENT_LIST_DIR}/../../_bin/${BOARD})
add_custom_command(TARGET app POST_BUILD
  COMMAND ${Python_EXECUTABLE} ${UF2CONV_PY} -f ${UF2_FAMILY_ID_${IDF_TARGET}} -b 0x0 -c -o ${CMAKE_BINARY_DIR}/update-tinyuf2.uf2 ${CMAKE_BINARY_DIR}/update-tinyuf2.bin
  COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_BINARY_DIR}/update-tinyuf2.uf2 ${ARTIFACT_PATH}/update-tinyuf2.uf2
  VERBATIM
  )

add_custom_target(flash-update-tinyuf2
  DEPENDS app
  COMMAND ${Python_EXECUTABLE} ${UF2CONV_PY} -f ${UF2_FAMILY_ID_${IDF_TARGET}} --deploy ${CMAKE_BINARY_DIR}/update-tinyuf2.uf2
  VERBATIM
  )
