if(SELFUPDATE_BUILD)
    return()
endif()

# Glue to build the self-update subproject binary as an external
# cmake project under this one
idf_build_get_property(build_dir BUILD_DIR)
set(SELFUPDATE_BUILD_DIR "${build_dir}/self_update")
set(SELFUPDATE_ELF_FILE "${SELFUPDATE_BUILD_DIR}/self_update.elf")
set(selfupdate_binary_files
    "${SELFUPDATE_ELF_FILE}"
    "${SELFUPDATE_BUILD_DIR}/self_update.bin"
    "${SELFUPDATE_BUILD_DIR}/self_update.map"
    )

idf_build_get_property(project_dir PROJECT_DIR)
idf_build_get_property(idf_path IDF_PATH)
idf_build_get_property(idf_target IDF_TARGET)
idf_build_get_property(sdkconfig SDKCONFIG)
idf_build_get_property(python PYTHON)
idf_build_get_property(extra_cmake_args EXTRA_CMAKE_ARGS)

externalproject_add(self_update
    SOURCE_DIR "${CMAKE_CURRENT_LIST_DIR}/subproject"
    BINARY_DIR "${SELFUPDATE_BUILD_DIR}"
    CMAKE_ARGS  -DIDF_PATH=${idf_path} -DIDF_TARGET=${idf_target}
                -DPYTHON_DEPS_CHECKED=1 -DPYTHON=${python}
                -DEXTRA_COMPONENT_DIRS=${CMAKE_CURRENT_LIST_DIR}
                -DPROJECT_SOURCE_DIR=${PROJECT_SOURCE_DIR}
                -DBOARD=${BOARD}
                -DUF2_FAMILY_ID=${UF2_FAMILY_ID}
                ${extra_cmake_args}
    INSTALL_COMMAND ""
    BUILD_ALWAYS 1  # no easy way around this...
    BUILD_BYPRODUCTS ${selfupdate_binary_files}
    )

# this is a hack due to an (annoying) shortcoming in cmake, it can't
# extend the 'clean' target to the external project
# see thread: https://cmake.org/pipermail/cmake/2016-December/064660.html
#
# So for now we just have the top-level build remove the final build products...
set_property(DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}" APPEND PROPERTY
    ADDITIONAL_CLEAN_FILES
    ${selfupdate_binary_files})
