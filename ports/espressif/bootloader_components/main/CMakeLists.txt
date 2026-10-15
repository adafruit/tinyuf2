set(bootloader_sources "bootloader_start.c")
set(bootloader_requires bootloader bootloader_support hal)
if(IDF_TARGET STREQUAL "esp32p4")
    list(APPEND bootloader_sources "double_reset_adc.c" "neopixel_p4.c")
    list(APPEND bootloader_requires efuse esp_hal_gpio esp_hal_ana_conv esp_hal_rmt)
endif()

idf_component_register(SRCS ${bootloader_sources}
                    INCLUDE_DIRS "../../boards/${BOARD}"
                    REQUIRES ${bootloader_requires})
