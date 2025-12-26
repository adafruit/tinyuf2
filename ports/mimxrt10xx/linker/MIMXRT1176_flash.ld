_itcm_base  = 0x00000000;
_itcm_size  = 256K;

_dtcm_base  = 0x20000000;
_dtcm_size  = 256K;

/* This is dedicated OCRAM. Not FlexRAM */
_ocram_base = 0x20240000;
_ocram_size = 1024K;

/* Flash addresses for direct flash boot
 * MIMXRT1176 expects FCFB at 0x400 offset, not 0x0 like 10xx series
 * Layout matches NXP SDK / MicroPython for MIMXRT1176:
 * - FCFB at 0x400
 * - IVT at 0x1000
 * - Vectors at 0x2000
 * - Text at 0x2400
 */
_fcfb_origin = 0x30000400;

/*
 * MIMXRT1176 Memory Layout
 *
 * +-----------------------------+
 * |         Text (Code)         |
 * |   0x30002400 - 0x3000AC00   |
 * |        (Len: 0x8800)        |
 * +-----------------------------+
 * |         Interrupts          |
 * |   0x30002000 - 0x30002400   |
 * |        (Len: 0x400)         |
 * +-----------------------------+
 * |             IVT             |
 * |   0x30001000 - 0x30002000   |
 * |        (Len: 0x1000)        |
 * +-----------------------------+
 * |            FCFB             |
 * |   0x30000400 - 0x30001000   |
 * |        (Len: 0xC00)         |
 * +-----------------------------+
 * |          Reserved           |
 * |   0x30000000 - 0x30000400   |
 * |        (Len: 0x400)         |
 * +-----------------------------+
 * |       m_data2 (OCRAM)       |
 * |   0x20240000 - 0x20340000   |
 * |       (Len: 0x100000)       |
 * +-----------------------------+
 * |        m_data (DTCM)        |
 * |   0x20000000 - 0x20040000   |
 * |       (Len: 0x40000)        |
 * +-----------------------------+
 */
