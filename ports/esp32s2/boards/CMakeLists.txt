idf_component_register(SRCS boards.c flash_hal.c
                       INCLUDE_DIRS "." "${BOARD}"
                       #PRIV_REQUIRES "driver"
                       REQUIRES spi_flash led_strip lcd)

