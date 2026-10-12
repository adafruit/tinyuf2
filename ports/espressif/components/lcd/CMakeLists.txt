idf_component_register(SRCS "lcd.c"
                       INCLUDE_DIRS "include"
                       REQUIRES boards esp_driver_spi
                       PRIV_REQUIRES esp_driver_gpio)
