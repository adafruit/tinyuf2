/* Application linker script for SAMD51x20 (1 MB flash, 256 KB HSRAM), runs behind the bootloader */

__flash_boot_size = DEFINED(__flash_boot_size) ? __flash_boot_size : 16K;
__flash_size = DEFINED(__flash_size) ? __flash_size : 1M;
__ram_size = DEFINED(__ram_size) ? __ram_size : 256K;

MEMORY
{
  FLASH (rx)  : ORIGIN = __flash_boot_size, LENGTH = __flash_size - __flash_boot_size
  RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = __ram_size
}
