/* Entry Point */
ENTRY(Reset_Handler)

/* Highest address of the user mode stack */
_estack = ORIGIN(SRAM) + LENGTH(SRAM);    /* end of RAM */
_board_dfu_dbl_tap = _estack;

MEMORY {
    ROM        (rx) : ORIGIN = 0x00000000,    LENGTH = 0x00020000 /* 128kB ROM */
    FLASH      (rx) : ORIGIN = 0x10000000 + __FLASH_BOOT_SIZE,    LENGTH = 3M - __FLASH_BOOT_SIZE
    SRAM      (rwx) : ORIGIN = 0x20000000,    LENGTH = 1M - 4 /* Reserve 4 for double tap */

	/*
     * Note that CS0/CS1 address mappings may be reversed using MXC_HPC->mbr0 and ->mbr1
     * The following mappings are selected for simplicity
     */
    HPB_CS0 (rwx)  : ORIGIN = 0x60000000, LENGTH = 0x10000000  /* External Hyperbus/Xccelabus chip select 0 */
    HPB_CS1 (rwx)  : ORIGIN = 0x70000000, LENGTH = 0x10000000  /* External Hyperbus/Xccelabus chip select 1 */
}
