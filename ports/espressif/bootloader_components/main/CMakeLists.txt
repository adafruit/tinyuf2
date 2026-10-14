set(bootloader_sources "bootloader_start.c" "double_reset_adc.c")
if(IDF_TARGET STREQUAL "esp32p4")
    list(APPEND bootloader_sources "neopixel_p4.c")
endif()

idf_component_register(SRCS ${bootloader_sources}
                    INCLUDE_DIRS "../../boards/${BOARD}"
                    REQUIRES bootloader bootloader_support efuse hal esp_hal_gpio esp_hal_ana_conv esp_hal_rmt)
