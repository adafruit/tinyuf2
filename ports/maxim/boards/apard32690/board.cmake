set(MAX_DEVICE max32690)
set(JLINK_DEVICE ${MAX_DEVICE})

function(update_board TARGET)
  target_sources(${TARGET} PUBLIC
    )
  target_compile_definitions(${TARGET} PUBLIC
    )
endfunction()
