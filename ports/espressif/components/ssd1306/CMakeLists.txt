set(component_srcs "ssd1306.c" "ssd1306_i2c.c" "ssd1306_spi.c")

idf_component_register(SRCS "${component_srcs}"
                       REQUIRES esp_driver_spi
                       PRIV_REQUIRES driver esp_driver_gpio
                       INCLUDE_DIRS ".")
