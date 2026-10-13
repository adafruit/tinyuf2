# Apply board specific content here
set(IDF_TARGET "esp32p4")

# Standalone apps (blinky, dfu_runtime, update_tinyuf2) must select the same P4 chip revision as TinyUF2
set(SDKCONFIG_DEFAULTS ${CMAKE_CURRENT_SOURCE_DIR}/sdkconfig.defaults ${CMAKE_CURRENT_LIST_DIR}/sdkconfig)
