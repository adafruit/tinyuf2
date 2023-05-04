_itcm_base  = 0x00000000;
_itcm_size  = 32K;

_dtcm_base  = 0x20000000;
_dtcm_size  = 32K;

_ocram_base = 0x20200000;
_ocram_size = 64K;

/* The bootrom uses up to 0x20207FFF */
_fcfb_origin = 0x20208000;

/* must be 4K aligned */
_ivt_origin = 0x20209000;
