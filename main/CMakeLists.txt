idf_component_register(SRCS flash_hal.c ghostfat.c main.c msc.c usb_descriptors.c
                    INCLUDE_DIRS "."
                    REQUIRES app_update boards led_strip spi_flash tinyusb lcd)
