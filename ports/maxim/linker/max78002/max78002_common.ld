SECTIONS {
    .rom :
    {
        KEEP(*(.rom_vector))
        *(.rom_handlers*)
    } > ROM

    .text :
    {
        _text = .;
        KEEP(*(.isr_vector))
        EXCLUDE_FILE (*riscv.o) *(.text*)    /* Program code (exclude RISCV code) */
        *(.rodata*)  /* read-only data: "const" */

        KEEP(*(.init))
        KEEP(*(.fini))

         /* .ctors */
        *crtbegin.o(.ctors)
        *crtbegin?.o(.ctors)
        *(EXCLUDE_FILE(*crtend?.o *crtend.o) .ctors)
        *(SORT(.ctors.*))
        *(.ctors)

        /* .dtors */
        *crtbegin.o(.dtors)
        *crtbegin?.o(.dtors)
        *(EXCLUDE_FILE(*crtend?.o *crtend.o) .dtors)
        *(SORT(.dtors.*))
        *(.dtors)

        /* C++ Exception handling */
        KEEP(*(.eh_frame*))
        _etext = .;
    } > FLASH

    .ARM.extab :
    {
        *(.ARM.extab* .gnu.linkonce.armextab.*)
    } > FLASH

    /* Binary import */
    .bin_storage :
    {
       FILL(0xFF)
      _bin_start_ = .;
      KEEP(*(.bin_storage_img))
      _bin_end_ = .;
      . = ALIGN(4);
    } > FLASH

    .rom_code :
    {
        . = ALIGN(16);
        _sran_code = .;
        *(.rom_code_section)
        _esran_code = .;
    } > ROM

    .flash_code :
    {
        . = ALIGN(16);
        _sran_code = .;
        *(.flash_code_section)
        _esran_code = .;
    } > FLASH

    .sram_code :
    {
        . = ALIGN(16);
        _sran_code = .;
        *(.sram_code_section)
        _esran_code = .;
    } > SRAM

    /* it's used for C++ exception handling      */
    /* we need to keep this to avoid overlapping */
    .ARM.exidx :
    {
        __exidx_start = .;
        *(.ARM.exidx* .gnu.linkonce.armexidx.*)
        __exidx_end = .;
    } > FLASH

    .data :
    {
        _data = ALIGN(., 4);
        _csi = . + 0x20000;
        *(vtable)
        *(.data*)           /*read-write initialized data: initialized global variable*/


        /* These array sections are used by __libc_init_array to call static C++ constructors */
        . = ALIGN(4);
        /* preinit data */
        PROVIDE_HIDDEN (__preinit_array_start = .);
        KEEP(*(.preinit_array))
        PROVIDE_HIDDEN (__preinit_array_end = .);

        . = ALIGN(4);
        /* init data */
        PROVIDE_HIDDEN (__init_array_start = .);
        KEEP(*(SORT(.init_array.*)))
        KEEP(*(.init_array))
        PROVIDE_HIDDEN (__init_array_end = .);

        . = ALIGN(4);
        /* finit data */
        PROVIDE_HIDDEN (__fini_array_start = .);
        KEEP(*(SORT(.fini_array.*)))
        KEEP(*(.fini_array))
        PROVIDE_HIDDEN (__fini_array_end = .);

        /* Run the flash programming functions from SRAM */
        *(.flashprog)

        _edata = ALIGN(., 4);

    } > SRAM AT>FLASH
    __load_data = LOADADDR(.data);

    .bss :
    {
        . = ALIGN(4);
        _bss = .;
        *(.bss*)     /*read-write zero initialized data: uninitialized global variable*/
        *(COMMON)
        _ebss = ALIGN(., 4);
    } > SRAM

    .shared :
    {
        . = ALIGN(4);
        _shared = .;
        *(.mailbox*)
        . = ALIGN(4);
        *(.shared*)     /*read-write zero initialized data: uninitialized global variable*/
        _eshared = ALIGN(., 4);
    } > SRAM
    __shared_data = LOADADDR(.shared);

    /* Set stack top to end of RAM, and stack limit move down by
     * size of stack_dummy section */
    __StackTop = ORIGIN(SRAM) + LENGTH(SRAM);
    __StackLimit = __StackTop - SIZEOF(.stack_dummy);

    /* .stack_dummy section doesn't contains any symbols. It is only
     * used for linker to calculate size of stack sections, and assign
     * values to stack symbols later */
    .stack_dummy (COPY):
    {
        *(.stack*)
    } > SRAM

    .heap (COPY):
    {
        . = ALIGN(4);
        PROVIDE ( end = . );
        PROVIDE ( _end = . );
        *(.heap*)
        __HeapLimit = ABSOLUTE(__StackLimit);
    } > SRAM

    PROVIDE(__stack = __StackTop);

    /* Check if data + heap + stack exceeds RAM limit */
    ASSERT(__StackLimit >= _ebss, "region RAM overflowed with stack")

    /* Section used by RISCV loader projects.  See RISCV_LOAD documentation in the build system. */
    .riscv_flash :
    {
        /* Align address to mod 256 with a small offset. This is required to match the flash page size.*/
        . = ALIGN(256); /* ALIGN operatator is used here.  Note that (. & 0x1FFFFF00) was used in the past, but a strange bug was seen on Windows where the & did not behave as expected.*/
        . += 0x100;
        _riscv_boot = .;
        KEEP(*riscv.o (.text*))
    } > FLASH
}
