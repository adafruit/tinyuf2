idf_component_register(REQUIRES esp_rom freertos soc driver)

idf_component_get_property( FREERTOS_ORIG_INCLUDE_PATH freertos ORIG_INCLUDE_PATH)

target_include_directories(${COMPONENT_TARGET} INTERFACE
    "${FREERTOS_ORIG_INCLUDE_PATH}"
    "${COMPONENT_DIR}/tinyusb/src"
    "."
)

target_sources(${COMPONENT_TARGET} INTERFACE    
    "${COMPONENT_DIR}/tinyusb/src/tusb.c"
    "${COMPONENT_DIR}/tinyusb/src/common/tusb_fifo.c"
    "${COMPONENT_DIR}/tinyusb/src/device/usbd.c"
    "${COMPONENT_DIR}/tinyusb/src/device/usbd_control.c"
    "${COMPONENT_DIR}/tinyusb/src/class/cdc/cdc_device.c"
    "${COMPONENT_DIR}/tinyusb/src/class/dfu/dfu_rt_device.c"
    "${COMPONENT_DIR}/tinyusb/src/class/hid/hid_device.c"
    "${COMPONENT_DIR}/tinyusb/src/class/midi/midi_device.c"
    "${COMPONENT_DIR}/tinyusb/src/class/msc/msc_device.c"
    "${COMPONENT_DIR}/tinyusb/src/class/net/net_device.c"
    "${COMPONENT_DIR}/tinyusb/src/class/usbtmc/usbtmc_device.c"
    "${COMPONENT_DIR}/tinyusb/src/class/vendor/vendor_device.c"
    "${COMPONENT_DIR}/tinyusb/src/portable/espressif/esp32s2/dcd_esp32s2.c"
)
