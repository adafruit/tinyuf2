include(${CMAKE_CURRENT_LIST_DIR}/boards/${BOARD}/board.cmake)

set(UF2_FAMILY_ID_esp32s2 0xbfdd4eee)
set(UF2_FAMILY_ID_esp32s3 0xc47e5767)
set(UF2_FAMILY_ID ${UF2_FAMILY_ID_${IDF_TARGET}})

# override default family_gen_uf2
function(family_gen_uf2 TARGET FAMILY_ID)
  add_custom_command(TARGET app POST_BUILD
    COMMAND ${Python_EXECUTABLE} ${UF2CONV_PY} -f ${FAMILY_ID} -b 0x0 -c -o ${CMAKE_BINARY_DIR}/${TARGET}.uf2 ${CMAKE_BINARY_DIR}/${TARGET}.bin
    COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_BINARY_DIR}/${TARGET}.uf2 ${ARTIFACT_PATH}/apps/${TARGET}.uf2
    VERBATIM
    )
endfunction()
