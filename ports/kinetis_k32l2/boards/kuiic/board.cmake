set(MCU K32L2B31A)
set(LD_FNAME K32L2B31xxxxA_flash.ld)
set(PYOCD_TARGET K32L2B3)

function(update_board TARGET)
  target_sources(${TARGET} PUBLIC
    ${SDK_DIR}/drivers/dma/fsl_dma.c
    ${SDK_DIR}/drivers/dmamux/fsl_dmamux.c
    ${SDK_DIR}/drivers/tpm/fsl_tpm.c
    ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/kuiic_rgb.c
    )
  target_include_directories(${TARGET} PUBLIC
    ${SDK_DIR}/drivers/dma
    ${SDK_DIR}/drivers/dmamux
    ${SDK_DIR}/drivers/tpm
    )
  target_compile_definitions(${TARGET} PUBLIC
    CPU_K32L2B31VLH0A
    )
endfunction()
