idf_component_register(SRCS boards/boards.c ghostfat.c main.c msc.c usb_descriptors.c
                    INCLUDE_DIRS "."
                    REQUIRES led_strip tinyusb)
