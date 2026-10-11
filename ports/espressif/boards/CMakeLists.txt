# IDF v6 removed the usb component (usb_phy is in esp_hw_support) and slimmed driver to legacy drivers
if (IDF_VERSION_MAJOR LESS 6)
  set(BOARD_PRIV_REQUIRES usb)
else ()
  set(BOARD_PRIV_REQUIRES esp_driver_gpio esp_driver_spi esp_driver_ledc esp_hal_usb)
endif ()

idf_component_register(SRCS boards.c board_flash.c ${BOARD_SOURCES}
                       INCLUDE_DIRS "." "${BOARD}" ${BOARD_INCLUDES} ${TOP}/src
                       PRIV_REQUIRES driver ${BOARD_PRIV_REQUIRES}
                       REQUIRES esp_timer app_update spi_flash led_strip lcd ssd1306 XPowersLib tinyusb_src)
