cmake_minimum_required(VERSION 3.17)

include(${CMAKE_CURRENT_LIST_DIR}/../../app.cmake)

set(app_src ${TOP}/apps/dfu_runtime/src)

add_executable(dfu_runtime
  board_dfu_runtime.c
  ${app_src}/main.c
  ${app_src}/nonce.c
  ${app_src}/usb_descriptors.c
  ${CMAKE_CURRENT_LIST_DIR}/../../boards.c
  ${TOP}/lib/mcu/nxp/mcux-sdk/drivers/common/fsl_common_arm.c
  ${TOP}/lib/tinyusb/src/portable/chipidea/ci_hs/dcd_ci_hs.c
  )
target_include_directories(dfu_runtime PUBLIC
  ${app_src}
  ${TOP}/src
  )

family_configure_app(dfu_runtime)
family_add_tinyusb(dfu_runtime OPT_MCU_MIMXRT1XXX)
family_gen_uf2(dfu_runtime ${UF2_FAMILY_ID})
family_flash_uf2(dfu_runtime ${UF2_FAMILY_ID})
