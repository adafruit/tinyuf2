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

/* The bootrom uses up to 0x2024BFFF, so we start at 0x2024C000.
 * FCFB at 0x2024C000, IVT at 0x2024D000 (must be 4K aligned).
 * This matches BOARD_BOOT_START = IVT - 0x1000 = FCFB */
_fcfb_origin = 0x2024C000;

/* must be 4K aligned */
_ivt_origin = 0x2024D000;
