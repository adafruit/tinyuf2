idf_component_register(SRCS "boards.c"
                       INCLUDE_DIRS "." "${BOARD}"
                       #PRIV_REQUIRES "driver"
                       REQUIRES led_strip lcd)

