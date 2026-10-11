# Note: bootloader_bin.c is generated into this project's binary dir by tinyuf2 app target
idf_component_register(SRCS ${TOP}/apps/self_update/self_update.c ${CMAKE_BINARY_DIR}/bootloader_bin.c
  INCLUDE_DIRS ${TOP}/src
  REQUIRES boards)
