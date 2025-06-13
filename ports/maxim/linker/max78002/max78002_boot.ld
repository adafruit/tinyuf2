/* Entry Point */
ENTRY(Reset_Handler)

/* Highest address of the user mode stack */
_estack = ORIGIN(SRAM) + LENGTH(SRAM);    /* end of RAM */
_board_dfu_dbl_tap = _estack;

MEMORY {
    ROM (rx)   : ORIGIN = 0x00000000, LENGTH = 0x00010000 /* 64 kB ROM */
    FLASH (rx) : ORIGIN = 0x10000000, LENGTH = __FLASH_BOOT_SIZE
    SRAM (rwx) : ORIGIN = 0x20000000, LENGTH = 0x00060000 - 4 /* Reserve 4 for double tap */
}
