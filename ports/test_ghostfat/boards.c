#include "common.h"

// From board_api.h

// HACK to execute our own functions, while using /src/main.c ....
//
// Option #1:
// * Always return `true` from `board_app_valid()`
// * Use board_app_jump() as the equivalent of `main()`
// * Note: will need to duplicate all the initialization code from `main()`...
// * Note: risk of breaking when `main()` changes
//
// Option #2:
// * define TINYUF2_DISPLAY as non-zero
// * Use `board_display_init()` as the equivalent of `main()`
// * Note: appears to also require other changes to compile
// * Note: risk of breaking when `main()` changes
// * Currently the option that most closely matches execution on real hardware
//
// Option #3:
// * Modify /src/main.c to support test-mode board
//
//
// Selected option #3.


//------------- Board  -------------//
void board_init(void) {};
void board_dfu_init(void) {}
void board_dfu_complete(void) { exit(0); } // defined in stdlib.h

//------------- app validation -------------//
bool board_app_valid(void) { return false; }
void board_app_jump(void) {
    // duplicate some initialization code
    board_dfu_init();
    board_flash_init();
    uf2_init();
    int returnCode = test_main();
    exit(returnCode); // must explicitly call exit()
} // cause the process to exit

//------------- Serial number -------------//
uint8_t board_usb_get_serial(uint8_t serial_id[16]) { (void) serial_id; return 0; }; // no serial number for testing

//------------- LEDs -------------//
void board_led_write(uint32_t value)      { (void)value; }
void board_rgb_write(uint8_t const rgb[]) { (void)rgb;   }

//------------- Timers -------------//
// TODO -- only if required to exercise ghostfat
void board_timer_start(uint32_t ms) { (void)ms; board_timer_handler(); };
void board_timer_stop(void) {};           // stop timer

//------------- Debug output -------------//
int board_uart_write(void const * buf, int len) { (void)buf; (void)len; return 0; }

//------------- Flash -------------//
void     board_flash_init(void) {}
uint32_t board_flash_size(void) { return CFG_UF2_FLASH_SIZE; }

void     board_flash_write(uint32_t addr, void const *data, uint32_t len) {
    (void)addr;
    (void)data;
    (void)len;
} // not supported
void     board_self_update(const uint8_t * bootloader_bin, uint32_t bootloader_len) {
    (void)bootloader_bin;
    (void)bootloader_len;
} // not supported
void     board_flash_flush(void) {}                                                    // not supported

#if TINYUF2_DISPLAY
void board_display_init(void) {
    int returnCode = test_main();
    exit(returnCode); // must explicitly call exit()
}
void board_display_draw_line(int y, uint16_t* pixel_color, uint32_t pixel_num) {
    (void)y;
    (void)pixel_color;
    (void)pixel_num;
}
void screen_draw_drag(void) {};
#endif



//------------- Interesting part of flash support for this test -------------//
void     board_flash_read (uint32_t addr, void* buffer, uint32_t len) {
    if ((addr & 7) != 0) {
        // TODO - need to copy part of the first eight bytes
        exit(1); // failure exit
        addr += 8 - (addr & 7);
    }

    // EMBED address in each 32 bits of the FLASH
    uint32_t * dest = buffer;
    size_t incBytes = sizeof(*dest);
    uint32_t currentAddress = addr;

    while (len >= incBytes) {
        memcpy(dest, &currentAddress, incBytes); // unaligned memory possible

        len -= incBytes;
        dest++;
        currentAddress += incBytes;
    }
}

