_itcm_base  = 0x00000000;
_itcm_size  = 128K;

_dtcm_base  = 0x20000000;
_dtcm_size  = 128K;

_ocram_base = 0x20200000;
_ocram_size = 256K;

/* Reference Manual suggests avoiding addresses 0x0 through 0x3 */
/* in section 9.6.1.2, so start at 0x1000 */
_fcfb_origin = 0x1000;

/* must be 4K aligned */
_ivt_origin = 0x2000;