idf_build_get_property(target IDF_TARGET)
string(TOUPPER ${target} target_upper)

set(app_src ${TOP}/apps/dfu_runtime/src)
set(tusb_src ${TOP}/lib/tinyusb/src)

idf_component_register(SRCS
    board_dfu_runtime.c
    ${app_src}/main.c
    ${app_src}/nonce.c
    ${app_src}/usb_descriptors.c
    ${tusb_src}/tusb.c
    ${tusb_src}/common/tusb_fifo.c
    ${tusb_src}/device/usbd.c
    ${tusb_src}/class/dfu/dfu_rt_device.c
    ${tusb_src}/portable/synopsys/dwc2/dcd_dwc2.c
    ${tusb_src}/portable/synopsys/dwc2/dwc2_common.c
  INCLUDE_DIRS ${app_src} ${tusb_src} ${TOP}/src ${FAMILY_PATH}/boards ${BOARD_PATH}
  PRIV_REQUIRES esp_timer esp_partition app_update esp_hal_usb)

target_compile_definitions(${COMPONENT_LIB} PRIVATE
  CFG_TUSB_MCU=OPT_MCU_${target_upper}
  CFG_TUSB_OS=OPT_OS_FREERTOS
  CFG_TUSB_OS_INC_PATH=freertos/)
