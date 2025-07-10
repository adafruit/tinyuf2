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
family_gen_uf2(blinky ${UF2_FAMILY_ID})
