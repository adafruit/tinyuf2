_fcfb_length = _ivt_origin - _fcfb_origin;
_ivt_length = 0x0400;

/* RT1064 is probably 0x7000C000 */
_interrupts_origin = 0x6000C000;
_interrupts_length = 0x0400;

_text_origin = _interrupts_origin + _interrupts_length;
_text_length =  0x8800;

/* Specify the memory areas */
MEMORY
{
  /* flash config and ivt are not used, leave here for compile only */
  m_flash_config        (RX)  : ORIGIN = _fcfb_origin       , LENGTH = _fcfb_length
  m_ivt                 (RX)  : ORIGIN = _ivt_origin        , LENGTH = _ivt_length

  m_interrupts          (RX)  : ORIGIN = _interrupts_origin , LENGTH = _interrupts_length
  m_text                (RX)  : ORIGIN = _text_origin       , LENGTH = _text_length
  m_data                (RW)  : ORIGIN = 0x20000000         , LENGTH = 32K
  m_data2               (RW)  : ORIGIN = _ocram_base        , LENGTH = _ocram_size
}
