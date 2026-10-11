idf_component_register(SRCS "lcd.c"
                       INCLUDE_DIRS "include"
                       REQUIRES boards
                       PRIV_REQUIRES esp_driver_gpio)
