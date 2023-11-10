cmake_minimum_required(VERSION 3.17)
include(${CMAKE_CURRENT_LIST_DIR}/../family_support.cmake)

project(tinyuf2)

add_executable(tinyuf2
  boards.c
  main.c
  ${TOP}/src/ghostfat.c
  )
target_include_directories(tinyuf2 PUBLIC
  ${TOP}/src
  ${TOP}/src/favicon
  .
  boards/${BOARD}
  )

set(GIT_VERSION 0.0.0-selftest)
set(GIT_SUBMODULE_VERSIONS "tinyusb (0.0.1-selftest)")

target_compile_definitions(tinyuf2 PUBLIC
  BOARD_UF2_FAMILY_ID=0x00000000
  UF2_VERSION_BASE="${GIT_VERSION}"
  UF2_VERSION="${GIT_VERSION} - ${GIT_SUBMODULE_VERSIONS}"
  COMPILE_DATE=\"Mar\ 11\ 2020\"
  COMPILE_TIME=\"17:35:07\"
  )

include(boards/${BOARD}/board.cmake)
update_board(tinyuf2)

if(NOT DEFINED CFG_UF2_FLASH_SIZE)
  set(CFG_UF2_FLASH_SIZE 0x00400000)
endif ()

target_compile_definitions(tinyuf2 PUBLIC
  CFG_UF2_FLASH_SIZE=${CFG_UF2_FLASH_SIZE}
  )

add_custom_target(mk-knowngood
  DEPENDS tinyuf2
  COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE_DIR:tinyuf2>/ghostfat.img ${CMAKE_BINARY_DIR}/knowngood.img
  COMMAND gzip ${CMAKE_BINARY_DIR}/knowngood.img
  COMMAND gzip --force --best ${CMAKE_BINARY_DIR}/knowngood.img.gz
  COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_BINARY_DIR}/knowngood.img.gz.gz ${CMAKE_CURRENT_LIST_DIR}/boards/${BOARD}/knowngood.img.gz.gz
  )
