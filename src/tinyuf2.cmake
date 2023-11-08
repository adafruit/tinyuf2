# This file is intended to be included in end-user CMakeLists.txt
# This file is NOT designed (on purpose) to be used as cmake
# subdir via add_subdirectory()
# The intention is to provide greater flexibility to users to
# create their own targets using the set variables.

function (add_tinyuf2 TARGET)
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

  execute_process(COMMAND git describe --dirty --always --tags OUTPUT_VARIABLE GIT_VERSION)
  string(STRIP ${GIT_VERSION} GIT_VERSION)

  get_target_property(deps_repo ${TARGET} DEPS_SUBMODULES)
  set(deps_repo "${deps_repo} ${TINYUSB_DIR}/..")

  execute_process(COMMAND bash "-c" "git -C ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/.. submodule status ${deps_repo} | cut -d\" \" -f3,4 | paste -s -d\" \" -"
    OUTPUT_VARIABLE GIT_SUBMODULE_VERSIONS
    )
  string(REPLACE ../ "" GIT_SUBMODULE_VERSIONS ${GIT_SUBMODULE_VERSIONS})
  string(REPLACE lib/ "" GIT_SUBMODULE_VERSIONS ${GIT_SUBMODULE_VERSIONS})
  string(STRIP ${GIT_SUBMODULE_VERSIONS} GIT_SUBMODULE_VERSIONS)

  target_compile_definitions(${TARGET} PUBLIC
    UF2_VERSION_BASE="${GIT_VERSION}"
    UF2_VERSION="${GIT_VERSION} - ${GIT_SUBMODULE_VERSIONS}"
    )
endfunction()
