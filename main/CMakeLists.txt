idf_component_register(SRCS main.c usb_descriptors.c msc_disk.c boards/boards.c
                    INCLUDE_DIRS "."
                    REQUIRES led_strip tinyusb)
