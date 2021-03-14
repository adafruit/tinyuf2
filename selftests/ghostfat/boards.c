#include "common.h"

// From board_api.h

//------------- Board  -------------//
void board_init(void) {};
void board_dfu_init(void) {}
void board_dfu_complete(void) { exit(0); } // defined in stdlib.h

//------------- app validation -------------//
bool board_app_valid(void) { return true; }
void board_app_jump(void) { exit(0); } // cause the process to exit

//------------- Serial number -------------//
uint8_t board_usb_get_serial(uint8_t serial_id[16]) { (void) serial_id; return 0; }; // no serial number for testing

//------------- LEDs -------------//
void board_led_write(uint32_t value)      { (void)value; }
void board_rgb_write(uint8_t const rgb[]) { (void)rgb;   }

//------------- Timers -------------//
// TODO -- only if required to exercise ghostfat
// void board_timer_start(uint32_t ms);   // start timer with ms interval
// void board_timer_stop(void);           // stop timer
// extern void board_timer_handler(void); // timer event handler, must be called by port/board

//------------- Debug output -------------//
int board_uart_write(void const * buf, int len) { (void)buf; (void)len; return 0; }

//------------- Flash -------------//
void     board_flash_init(void) {}
uint32_t board_flash_size(void) { return 4MiB_FLASH_SIZE; }

void     board_flash_write(uint32_t addr, void const *data, uint32_t len) {}           // not supported
void     board_self_update(const uint8_t * bootloader_bin, uint32_t bootloader_len) {} // not supported
void     board_flash_flush(void) {}                                                    // not supported

//------------- Interesting part of flash support for this test -------------//
void     board_flash_read (uint32_t addr, void* buffer, uint32_t len) {
    if ((addr & 7) != 0) {
        // TODO - need to copy part of the first eight bytes
        exit(1); // failure exit
        addr += 8 - (addr & 7);
    }

    // EMBED address in each 64 bits of the FLASH
    uint64_t * dest = buffer;
    size_t incBytes = sizeof(*dest);
    uint64_t currentAddress = addr;

    while (len >= incBytes) {
        memcpy(dest, currentAddress, incBytes); // unaligned memory possible

        len -= incBytes;
        dest++;
        currentAddress += incBytes;
    }
}

