cmake_minimum_required(VERSION 3.17)
include(${CMAKE_CURRENT_LIST_DIR}/../family_support.cmake)
project(tinyuf2 C ASM)
set(CMAKE_EXECUTABLE_SUFFIX .elf)

add_executable(tinyuf2
  boards.c
  board_flash.c
  ${TOP}/lib/tinyusb/src/portable/wch/wch_hs2/dcd_wch_hs2.c
  )
target_link_options(tinyuf2 PUBLIC
  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/linker/ch32v4x7_boot.ld"
  "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/linker/ch32v4x7_common.ld"
)
family_configure_tinyuf2(tinyuf2 OPT_MCU_CH32V4X7)

# needs an openocd whose WCH-LinkE driver attaches to CH32V4x7 (hathach/openocd)
set(OPENOCD_OPTION "-f target/wch-riscv.cfg")
family_flash_openocd(tinyuf2 hex)

family_add_app(blinky ${TOP}/apps/blinky)
