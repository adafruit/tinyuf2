/* Application linker script for SAMD51, runs behind the bootloader; sizes from the board */

MEMORY
{
  FLASH (rx)  : ORIGIN = __flash_boot_size, LENGTH = __flash_size - __flash_boot_size
  RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = __ram_size
}
