idf_component_register(SRCS ${TOP}/apps/self_update/self_update.c ${CMAKE_CURRENT_BINARY_DIR}/bootloader_bin.c
  INCLUDE_DIRS ${TOP}/src
  REQUIRES boards)

# Generate bootloader_bin.c
add_custom_command(OUTPUT bootloader_bin.c
  COMMAND ${Python_EXECUTABLE} ${UF2CONV_PY} --carray -o bootloader_bin.c ${CMAKE_BINARY_DIR}/../tinyuf2.bin
  )

add_custom_target(bootloader_bin DEPENDS bootloader_bin.c)

add_dependencies(${COMPONENT_LIB} bootloader_bin)
set_property(DIRECTORY "${COMPONENT_DIR}" APPEND PROPERTY
  ADDITIONAL_CLEAN_FILES bootloader_bin.c)

cmake_print_variables(elf COMPONENT_LIB)
add_custom_command(TARGET ${COMPONENT_LIB} POST_BUILD
  COMMAND ${Python_EXECUTABLE} ${UF2CONV_PY} -f ${UF2_FAMILY_ID} -b 0x0 -c -o ${CMAKE_BINARY_DIR}/update-tinyuf2.uf2 ${CMAKE_BINARY_DIR}/update-tinyuf2.bin
  VERBATIM)
