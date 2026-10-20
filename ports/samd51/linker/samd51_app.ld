/* Application linker script for SAMD51x20 (1 MB flash, 256 KB HSRAM), runs behind the bootloader */

__flash_boot_size = DEFINED(__flash_boot_size) ? __flash_boot_size : 16K;
__flash_size = DEFINED(__flash_size) ? __flash_size : 1M;
__ram_size = DEFINED(__ram_size) ? __ram_size : 256K;

OUTPUT_FORMAT("elf32-littlearm", "elf32-littlearm", "elf32-littlearm")
OUTPUT_ARCH(arm)
ENTRY(Reset_Handler)

/* Highest address of the stack */
_estack = ORIGIN(RAM) + LENGTH(RAM);

_Min_Stack_Size = 0x800;

MEMORY
{
  FLASH (rx)  : ORIGIN = __flash_boot_size, LENGTH = __flash_size - __flash_boot_size
  RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = __ram_size
}

SECTIONS
{
  .text :
  {
    . = ALIGN(4);
    _sfixed = .;
    KEEP(*(.vectors .vectors.*))
    *(.text .text.* .gnu.linkonce.t.*)
    *(.glue_7t) *(.glue_7)
    *(.rodata .rodata* .gnu.linkonce.r.*)
    *(.ARM.extab* .gnu.linkonce.armextab.*)

    . = ALIGN(4);
    KEEP(*(.init))
    . = ALIGN(4);
    __preinit_array_start = .;
    KEEP(*(.preinit_array))
    __preinit_array_end = .;

    . = ALIGN(4);
    __init_array_start = .;
    KEEP(*(SORT(.init_array.*)))
    KEEP(*(.init_array))
    __init_array_end = .;

    . = ALIGN(4);
    KEEP(*(.fini))

    . = ALIGN(4);
    __fini_array_start = .;
    KEEP(*(.fini_array))
    KEEP(*(SORT(.fini_array.*)))
    __fini_array_end = .;

    . = ALIGN(4);
    _efixed = .;
  } > FLASH

  .ARM.exidx :
  {
    __exidx_start = .;
    *(.ARM.exidx* .gnu.linkonce.armexidx.*)
    __exidx_end = .;
  } > FLASH

  . = ALIGN(4);
  _etext = .;

  .relocate :
  {
    . = ALIGN(4);
    _srelocate = .;
    *(.ramfunc .ramfunc.*)
    *(.data .data.*)
    . = ALIGN(4);
    _erelocate = .;
  } > RAM AT> FLASH

  .bss (NOLOAD) :
  {
    . = ALIGN(4);
    _sbss = .;
    _szero = .;
    *(.bss .bss.*)
    *(COMMON)
    . = ALIGN(4);
    _ebss = .;
    _ezero = .;
  } > RAM

  /* Fails the link if the stack has less than _Min_Stack_Size left */
  ._stack_check (NOLOAD) :
  {
    . = ALIGN(8);
    PROVIDE(end = .);
    PROVIDE(_end = .);
    . = . + _Min_Stack_Size;
  } > RAM

  .ARM.attributes 0 : { *(.ARM.attributes) }
}
