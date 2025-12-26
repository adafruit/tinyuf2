_itcm_base  = 0x00000000;
_itcm_size  = 128K;

_dtcm_base  = 0x20000000;
_dtcm_size  = 128K;

_ocram_base = 0x20200000;
_ocram_size = 256K;

/* The bootrom uses up to 0x20207FFF */

/* The default FlexRAM config has 128k ITCM so use it. */

/* Reference Manual suggests avoiding addresses 0x0 through 0x3 */
/* in section 9.6.1.2, so start at 0x1000 */
_fcfb_origin = 0x20208000;

_flash_base = 0x70000000;

/*
 * MIMXRT1064 Memory Layout
 *
 * +-----------------------------+
 * |         Text (Code)         |
 * |   0x2020A400 - 0x202123FF   |
 * |        (Len: 0x8000)        |
 * +-----------------------------+
 * |         Interrupts          |
 * |   0x2020A000 - 0x2020A3FF   |
 * |        (Len: 0x400)         |
 * +-----------------------------+
 * |             IVT             |
 * |   0x20209000 - 0x20209FFF   |
 * |        (Len: 0x1000)        |
 * +-----------------------------+
 * |            FCFB             |
 * |   0x20208000 - 0x20208FFF   |
 * |        (Len: 0x1000)        |
 * +-----------------------------+
 * |           BootROM           |
 * |   0x20200000 - 0x20207FFF   |
 * |        (Len: 0x8000)        |
 * +-----------------------------+
 * |       m_data2 (OCRAM)       |
 * |   0x20200000 - 0x2023FFFF   |
 * |       (Len: 0x40000)        |
 * +-----------------------------+
 * |        m_data (DTCM)        |
 * |   0x20000000 - 0x2001FFFF   |
 * |       (Len: 0x20000)        |
 * +-----------------------------+
 */
