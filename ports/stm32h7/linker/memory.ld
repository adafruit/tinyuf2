/* Need at least 12 bytes of noinit memory */
/* _board_dfu_dbl_tap - 4 bytes */
/* _board_tmp_boot_addr - 4 bytes */
/* _board_tmp_boot_magic - 4 bytes */
ASSERT(_noinit_size >= 0xC, "Need at least 12 bytes of no-init")

MEMORY
{
  FLASH       (rx)  : ORIGIN = _flash_origin,   LENGTH = _flash_size
  RAM         (xrw) : ORIGIN = _ram_origin,     LENGTH = _ram_size
  NOINIT      (xrw) : ORIGIN = _noinit_origin,  LENGTH = _noinit_size
}
