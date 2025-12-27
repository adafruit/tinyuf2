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

/* The bootrom uses up to 0x2024BFFF. Keep a 0x400 gap so FCFB matches flash offset. */
_fcfb_origin = 0x2024C400;

_flash_base = 0x30000000;

/*
 * MIMXRT1176 Memory Layout
 *
 *           RAM Executed                       Flash Stored
 * +-----------------------------+
 * |       m_data2 (OCRAM)       |
 * |   0x20280000 - 0x2029FFFF   |
 * |        (Len: 0x20000)       |
 * +-----------------------------+
 * +-----------------------------+
 * |        m_data (DTCM)        |
 * |   0x20260000 - 0x2027FFFF   |
 * |        (Len: 0x20000)       |
 * +-----------------------------+
 * +-----------------------------+    +-----------------------------+
 * |         Text (Code)         |    |         Text (Code)         |
 * |   0x2024E400 - 0x202563FF   |    |   0x30002400 - 0x3000A3FF   |
 * |        (Len: 0x8000)        |    |        (Len: 0x8000)        |
 * +-----------------------------+    +-----------------------------+
 * +-----------------------------+    +-----------------------------+
 * |          Interrupts         |    |          Interrupts         |
 * |   0x2024E000 - 0x2024E3FF   |    |   0x30002000 - 0x300023FF   |
 * |         (Len: 0x400)        |    |         (Len: 0x400)        |
 * +-----------------------------+    +-----------------------------+
 * +-----------------------------+    +-----------------------------+
 * |             IVT             |    |             IVT             |
 * |   0x2024D000 - 0x2024DFFF   |    |   0x30001000 - 0x30001FFF   |
 * |        (Len: 0x1000)        |    |        (Len: 0x1000)        |
 * +-----------------------------+    +-----------------------------+
 * +-----------------------------+    +-----------------------------+
 * |             FCFB            |    |             FCFB            |
 * |   0x2024C400 - 0x2024CFFF   |    |   0x30000400 - 0x30000FFF   |
 * |        (Len: 0x0C00)        |    |        (Len: 0x0C00)        |
 * +-----------------------------+    +-----------------------------+
 * +-----------------------------+
 * |           Reserved          |
 * |   0x2024C000 - 0x2024C3FF   |
 * |         (Len: 0x400)        |
 * +-----------------------------+
 * +-----------------------------+
 * |           BootROM           |
 * |   0x20240000 - 0x2024BFFF   |
 * |        (Len: 0xC000)        |
 * +-----------------------------+
 */
