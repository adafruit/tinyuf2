fcb_length = 0x0C00;

/* offset 0x1000 */
ivt_origin = fcb_origin + fcb_length;
ivt_length = 0x0400;

/* offset 0x1400 */
interrupts_origin = ivt_origin + ivt_length;
interrupts_length = 0x0400;

/* offset 0x1800 */
text_origin = interrupts_origin + interrupts_length;
text_length =  0x8800;

/* Specify the memory areas */
MEMORY
{
  m_flash_config        (RX)  : ORIGIN = fcb_origin        , LENGTH = fcb_length
  m_ivt                 (RX)  : ORIGIN = ivt_origin        , LENGTH = ivt_length
  m_interrupts          (RX)  : ORIGIN = interrupts_origin , LENGTH = interrupts_length
  m_text                (RX)  : ORIGIN = text_origin       , LENGTH = text_length

  m_data                (RW)  : ORIGIN = dtcm_base         , LENGTH = dtcm_size - 4 /* 4 bytes for double tap */
  m_data2               (RW)  : ORIGIN = ocram_base        , LENGTH = ocram_size
}
