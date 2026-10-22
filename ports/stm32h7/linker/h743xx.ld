/* RM0433 - Table 7 */

/* PFLASH: TinyUF2 in bank 1 sector 0, apps (PFLASH_APP) from sector 1 to the end of bank 2 */
_flash_origin = DEFINED(PFLASH_APP) ? 0x08020000 : 0x08000000;
_flash_size = DEFINED(PFLASH_APP) ? 2048K - 128K : 128K;

/* DTCM */
_ram_origin = 0x20000000;
_ram_size = 64K;

_noinit_origin = _ram_origin + _ram_size;
_noinit_size = 12;
