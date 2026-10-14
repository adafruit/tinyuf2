function(update_board TARGET)
  target_compile_definitions(${TARGET} PUBLIC
    TINYUF2_FAVICON_HEADER="favicon_adafruit_256.h"
    )
endfunction()
