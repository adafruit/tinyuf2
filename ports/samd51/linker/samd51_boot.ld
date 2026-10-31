/* Bootloader linker script for SAMD51x20 (1 MB flash, 256 KB HSRAM) */

__flash_boot_size = DEFINED(__flash_boot_size) ? __flash_boot_size : 16K;
__ram_size = DEFINED(__ram_size) ? __ram_size : 256K;

MEMORY
{
  FLASH (rx)  : ORIGIN = 0x00000000, LENGTH = __flash_boot_size
  RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = __ram_size
}
