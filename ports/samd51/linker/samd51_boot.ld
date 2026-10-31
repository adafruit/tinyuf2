/* Bootloader linker script for SAMD51x20 (1 MB flash, 256 KB HSRAM) */

MEMORY
{
  FLASH (rx)  : ORIGIN = 0x00000000, LENGTH = __flash_boot_size
  RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = __ram_size
}
