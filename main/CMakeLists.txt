idf_component_register(SRCS boards/boards.c flash_hal.c ghostfat.c main.c msc.c usb_descriptors.c
                    INCLUDE_DIRS "."
                    REQUIRES app_update led_strip spi_flash tinyusb)
