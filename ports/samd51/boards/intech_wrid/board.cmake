set(LD_FLASH_BOOT_SIZE 16K)
set(LD_FLASH_SIZE 1M)
set(LD_RAM_SIZE 256K)

function(update_board TARGET)
  target_compile_definitions(${TARGET} PUBLIC
    __SAMD51N20A__
    )
endfunction()
