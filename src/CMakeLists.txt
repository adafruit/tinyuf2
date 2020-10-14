idf_component_register(SRCS ghostfat.c images.c main.c msc.c screen.c usb_descriptors.c
                    INCLUDE_DIRS "."
                    REQUIRES app_update boards led_strip spi_flash tinyusb lcd)
