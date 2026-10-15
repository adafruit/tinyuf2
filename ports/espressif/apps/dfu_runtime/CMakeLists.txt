# The following five lines of boilerplate have to be in your project's
# CMakeLists in this exact order for cmake to work correctly
cmake_minimum_required(VERSION 3.17)

include(${CMAKE_CURRENT_LIST_DIR}/../../../family_support.cmake)

# No shared boards/tinyusb_src components: the app has its own TinyUSB configuration and no board_flash.c
set(SDKCONFIG ${CMAKE_BINARY_DIR}/sdkconfig)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
idf_build_set_property(DEPENDENCIES_LOCK ${CMAKE_BINARY_DIR}/dependencies.lock) # keep the source tree clean

project(dfu_runtime)
family_gen_uf2(dfu_runtime ${UF2_FAMILY_ID})
