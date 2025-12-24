_itcm_base  = 0x00000000;
_itcm_size  = 256K;

/* For RAM boot via SDP, DTCM is not accessible because FlexRAM
 * isn't configured by the ROM bootloader. Use OCRAM instead.
 * Place data/bss/stack in upper OCRAM area, after our code. */
_dtcm_base  = 0x20260000;
_dtcm_size  = 128K;

/* This is dedicated OCRAM. Not FlexRAM */
_ocram_base = 0x20280000;
_ocram_size = 128K;

/* The bootrom uses up to 0x2024BFFF, so we start FCFB at 0x2024C000 */
_fcfb_origin = 0x2024C000;

/*
 * MIMXRT1176 Memory Layout
 *
 * +-----------------------------+
 * |       m_data2 (OCRAM)       |
 * |   0x20280000 - 0x202A0000   |
 * |       (Len: 0x20000)        |
 * +-----------------------------+
 * |        m_data (DTCM)        |
 * |   0x20260000 - 0x20280000   |
 * |       (Len: 0x20000)        |
 * +-----------------------------+
 * |         Text (Code)         |
 * |   0x2024E400 - 0x20256400   |
 * |        (Len: 0x8000)        |
 * +-----------------------------+
 * |         Interrupts          |
 * |   0x2024E000 - 0x2024E400   |
 * |        (Len: 0x400)         |
 * +-----------------------------+
 * |             IVT             |
 * |   0x2024D000 - 0x2024E000   |
 * |        (Len: 0x1000)        |
 * +-----------------------------+
 * |            FCFB             |
 * |   0x2024C000 - 0x2024D000   |
 * |        (Len: 0x1000)        |
 * +-----------------------------+
 * |           BootROM           |
 * |   0x20240000 - 0x2024C000   |
 * |        (Len: 0xC000)        |
 * +-----------------------------+
 */
