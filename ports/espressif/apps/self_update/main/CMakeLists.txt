# Note: bootloader_bin.c is generated by tinyuf2 app target
idf_component_register(SRCS ${TOP}/apps/self_update/self_update.c bootloader_bin.c
  INCLUDE_DIRS ${TOP}/src
  REQUIRES boards)
