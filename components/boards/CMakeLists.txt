idf_component_register(SRCS boards.c
                       INCLUDE_DIRS "." "${BOARD}"
                       #PRIV_REQUIRES "driver"
                       REQUIRES led_strip led_strip_spi_apa102 lcd)

