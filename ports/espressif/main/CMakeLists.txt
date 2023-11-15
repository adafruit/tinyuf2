set(srcs
  ${TOP}/src/ghostfat.c
  ${TOP}/src/images.c
  ${TOP}/src/main.c
  ${TOP}/src/msc.c
  ${TOP}/src/screen.c
  ${TOP}/src/usb_descriptors.c
  )

idf_component_register(SRCS ${srcs}
                    INCLUDE_DIRS ${TOP}/src ${TOP}/src/favicon
                    REQUIRES boards tinyusb_src)
