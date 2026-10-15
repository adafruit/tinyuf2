function(update_board TARGET)
  target_compile_definitions(${TARGET} PUBLIC
    TINYUF2_FAVICON_HEADER="favicon_adafruit_256.h"
    CFG_UF2_NUM_BLOCKS=265000
    CFG_UF2_SECTORS_PER_CLUSTER=64
    )
endfunction()
