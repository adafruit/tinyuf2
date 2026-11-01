/* Bootloader linker script for SAMD51, sizes from the board (__flash_boot_size, __ram_size) */

MEMORY
{
  FLASH (rx)  : ORIGIN = 0x00000000, LENGTH = __flash_boot_size
  RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = __ram_size
}
