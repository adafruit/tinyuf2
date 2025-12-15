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

/* IVT at 0x1000 offset */
_ivt_origin = 0x30001000;
