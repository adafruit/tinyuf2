include(${CMAKE_CURRENT_LIST_DIR}/boards/${BOARD}/board.cmake)

set(UF2_FAMILY_ID_esp32s2 0xbfdd4eee)
set(UF2_FAMILY_ID_esp32s3 0xc47e5767)
set(UF2_FAMILY_ID ${UF2_FAMILY_ID_${IDF_TARGET}})
