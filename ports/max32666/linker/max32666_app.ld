/* Entry Point */
ENTRY(Reset_Handler)

/* Highest address of the user mode stack */
_estack = ORIGIN(SRAM) + LENGTH(SRAM);    /* end of RAM */
_board_dfu_dbl_tap = _estack;

/* SPID and SPIX Sections here are maximum possible sizes */
/* If used, they should be adjusted for the external Flash/RAM size */
MEMORY {

    SPIX (rx)  : ORIGIN = 0x08000000, LENGTH = 0x08000000
    FLASH (rx) : ORIGIN = 0x10000000 + __FLASH_BOOT_SIZE, LENGTH = 1M - __FLASH_BOOT_SIZE
    SRAM (rwx) : ORIGIN = 0x20000000, LENGTH = 0x0008C000 - 4 /* Reserve 4 for double tap */
    SPID (rw)  : ORIGIN = 0x80000000, LENGTH = 512M
}
