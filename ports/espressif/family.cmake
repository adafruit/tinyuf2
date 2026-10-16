include(${CMAKE_CURRENT_LIST_DIR}/boards/${BOARD}/board.cmake)

if(IDF_TARGET STREQUAL "esp32p4")
  # TinyUF2 and the apps run on OTG HS unless the board routes OTG FS
  if(NOT DEFINED BOARD_TUD_RHPORT)
    set(BOARD_TUD_RHPORT 1)
  endif()
  add_compile_definitions(BOARD_TUD_RHPORT=${BOARD_TUD_RHPORT})
  # Chip revisions <3.0 and >=3.0 need separate images: standalone apps take the board sdkconfig, which selects one
  set(SDKCONFIG_DEFAULTS ${CMAKE_CURRENT_SOURCE_DIR}/sdkconfig.defaults ${BOARD_PATH}/sdkconfig)
endif()

set(UF2_FAMILY_ID_esp32s2 0xbfdd4eee)
set(UF2_FAMILY_ID_esp32s3 0xc47e5767)
set(UF2_FAMILY_ID_esp32p4 0x3d308e94)
set(UF2_FAMILY_ID_esp32s31 0x3101f7c1)
set(UF2_FAMILY_ID ${UF2_FAMILY_ID_${IDF_TARGET}})

# override default family_gen_uf2
function(family_gen_uf2 TARGET FAMILY_ID)
  add_custom_command(TARGET app POST_BUILD
    COMMAND ${Python_EXECUTABLE} ${UF2CONV_PY} -f ${FAMILY_ID} -b 0x0 -c -o ${CMAKE_BINARY_DIR}/${TARGET}.uf2 ${CMAKE_BINARY_DIR}/${TARGET}.bin
    COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_BINARY_DIR}/${TARGET}.uf2 ${ARTIFACT_PATH}/apps/${TARGET}.uf2
    VERBATIM
    )
endfunction()
