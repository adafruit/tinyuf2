set(JLINK_DEVICE ATSAMD51J19)

set(LD_FLASH_BOOT_SIZE 16K)
set(LD_FLASH_SIZE 512K)
set(LD_RAM_SIZE 192K)

function(update_board TARGET)
  target_compile_definitions(${TARGET} PUBLIC
    __SAMD51J19A__
    )
endfunction()
