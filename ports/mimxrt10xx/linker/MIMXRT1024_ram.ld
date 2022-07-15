_itcm_base  = 0x00000000;
_itcm_size  = 64K;

_dtcm_base  = 0x20000000;
_dtcm_size  = 64K;

_ocram_base = 0x20200000;
_ocram_size = 128K;

/* Avoid ITCM address 0x0, start at 4K
  See note in RT1020 Reference Manual section 9.6.1.2 FlexSPI Serial NOR Flash Boot Operation */
_fcfb_origin = 0x1000;

/* must be 4K aligned */
_ivt_origin = 0x2000;
