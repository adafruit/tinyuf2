/* Define default values if not already defined */
__FLASH_SIZE = DEFINED(__flash_size) ? __flash_size : 512K;
__flash_boot_size = 32K;
__flash_app_size = __FLASH_SIZE - __flash_boot_size;

__RAM_SIZE = DEFINED(__ram_size) ? __ram_size : 200K;

MEMORY
{
  FLASH (rx) : ORIGIN = 0x00000000, LENGTH = __flash_boot_size
  RAM (xrw) : ORIGIN = 0x20000000, LENGTH = __RAM_SIZE
}
