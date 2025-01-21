idf_component_register(SRCS boards.c board_flash.c ${BOARD_SOURCES}
                       INCLUDE_DIRS "." "${BOARD}" ${BOARD_INCLUDES} ${TOP}/src
                       PRIV_REQUIRES driver usb
                       REQUIRES esp_timer app_update spi_flash led_strip lcd ssd1306 XPowersLib tinyusb_src)
