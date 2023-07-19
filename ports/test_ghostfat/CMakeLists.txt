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
target_compile_definitions(tinyuf2 PUBLIC
  BOARD_UF2_FAMILY_ID=0x00000000
  COMPILE_DATE=\"Mar\ 11\ 2020\"
  COMPILE_TIME=\"17:35:07\"
  )

family_add_uf2version(tinyuf2 tinyusb)

include(boards/${BOARD}/board.cmake)
update_board(tinyuf2)
