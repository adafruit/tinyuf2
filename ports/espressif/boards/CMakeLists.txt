idf_component_register(SRCS boards.c board_flash.c ${BOARD_SOURCES}
                       INCLUDE_DIRS "." "${BOARD}" ${BOARD_INCLUDES} ${TOP}/src
                       PRIV_REQUIRES esp_driver_gpio esp_driver_i2c esp_driver_spi esp_driver_ledc esp_hal_usb
                       REQUIRES esp_timer app_update spi_flash led_strip lcd ssd1306 XPowersLib tinyusb_src)
