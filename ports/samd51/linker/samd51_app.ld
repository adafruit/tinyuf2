/* Application linker script for SAMD51x20 (1 MB flash, 256 KB HSRAM), runs behind the bootloader */

MEMORY
{
  FLASH (rx)  : ORIGIN = __flash_boot_size, LENGTH = __flash_size - __flash_boot_size
  RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = __ram_size
}
