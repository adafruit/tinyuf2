function(update_board TARGET)
  target_compile_definitions(${TARGET} PUBLIC
    CFG_UF2_SECTORS_PER_CLUSTER=8
    )
endfunction()
