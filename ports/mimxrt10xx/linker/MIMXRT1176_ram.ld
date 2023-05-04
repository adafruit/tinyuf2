_itcm_base  = 0x00000000;
_itcm_size  = 256K;

_dtcm_base  = 0x20000000;
_dtcm_size  = 256K;

/* This is dedicated OCRAM. Not FlexRAM */
_ocram_base = 0x20240000;
_ocram_size = 1024K;

/* The bootrom uses up to 0x2024BFFF */

_fcfb_origin = 0x2024C400;

/* must be 4K aligned */
_ivt_origin = 0x2024D000;
