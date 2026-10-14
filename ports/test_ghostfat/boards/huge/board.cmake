set(CFG_UF2_FLASH_SIZE 0x10000000)

function(update_board TARGET)
  target_compile_definitions(${TARGET} PUBLIC
    CFG_UF2_NUM_BLOCKS=0x300000
    CFG_UF2_SECTORS_PER_CLUSTER=64
    )
endfunction()
