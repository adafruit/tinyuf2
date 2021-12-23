idf_component_register(SRCS boards.c board_flash.c
                       INCLUDE_DIRS "." "${BOARD}"
                       #PRIV_REQUIRES "driver"
                       REQUIRES app_update spi_flash led_strip lcd)

idf_component_get_property( FREERTOS_ORIG_INCLUDE_PATH freertos ORIG_INCLUDE_PATH)

target_include_directories(${COMPONENT_TARGET} PUBLIC
  "${FREERTOS_ORIG_INCLUDE_PATH}"
  "${TOP}/src"
  "${TOP}/lib/tinyusb/src"
  "${TOP}/ports/espressif"
)