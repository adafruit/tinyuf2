# This file is intended to be included in end-user CMakeLists.txt
# This file is NOT designed (on purpose) to be used as cmake
# subdir via add_subdirectory()
# The intention is to provide greater flexibility to users to
# create their own targets using the set variables.

function (add_tinyuf2_src TARGET)
  target_sources(${TARGET} PUBLIC
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/ghostfat.c
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/images.c
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/main.c
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/msc.c
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/screen.c
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/usb_descriptors.c
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/board_api.h
    )
  target_include_directories(${TARGET} PUBLIC
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/favicon
    )
endfunction()
