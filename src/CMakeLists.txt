idf_component_register(SRCS ghostfat.c images.c main.c msc.c screen.c usb_descriptors.c
                    INCLUDE_DIRS "."
                    REQUIRES boards)

idf_component_get_property( FREERTOS_ORIG_INCLUDE_PATH freertos ORIG_INCLUDE_PATH)

target_include_directories(${COMPONENT_TARGET} PUBLIC
  "${FREERTOS_ORIG_INCLUDE_PATH}"
  "${TOP}/lib/tinyusb/src"
  "${TOP}/ports/esp32s2"
)

target_sources(${COMPONENT_TARGET} PUBLIC
  "${TOP}/lib/tinyusb/src/tusb.c"
  "${TOP}/lib/tinyusb/src/common/tusb_fifo.c"
  "${TOP}/lib/tinyusb/src/device/usbd.c"
  "${TOP}/lib/tinyusb/src/device/usbd_control.c"
  "${TOP}/lib/tinyusb/src/class/cdc/cdc_device.c"
  "${TOP}/lib/tinyusb/src/class/dfu/dfu_rt_device.c"
  "${TOP}/lib/tinyusb/src/class/hid/hid_device.c"
  "${TOP}/lib/tinyusb/src/class/midi/midi_device.c"
  "${TOP}/lib/tinyusb/src/class/msc/msc_device.c"
  "${TOP}/lib/tinyusb/src/class/net/net_device.c"
  "${TOP}/lib/tinyusb/src/class/usbtmc/usbtmc_device.c"
  "${TOP}/lib/tinyusb/src/class/vendor/vendor_device.c"
  "${TOP}/lib/tinyusb/src/portable/espressif/esp32s2/dcd_esp32s2.c"
)