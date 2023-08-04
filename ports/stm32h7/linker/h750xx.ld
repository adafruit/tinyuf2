/* RM0433 - Table 7 */

/* PFLASH bank 1 or AXISRAM*/
_flash_origin = DEFINED(RAMCODE) ? 0x24000000 : 0x08000000;
_flash_size = 128K;

/* DTCM */
_ram_origin = 0x20000000;
_ram_size = 64K;

_noinit_origin = _ram_origin + _ram_size;
_noinit_size = 12;
