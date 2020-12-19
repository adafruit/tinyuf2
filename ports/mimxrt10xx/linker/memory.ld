/* Specify the memory areas */
MEMORY
{
  m_flash_config        (RX)  : ORIGIN = m_fcfb_origin, LENGTH = 0x00000C00 /* fcfb */
  m_ivt                 (RX)  : ORIGIN = m_ivt_origin, LENGTH = 0x00000400
  m_interrupts          (RX)  : ORIGIN = m_int_origin, LENGTH = 0x00000400
  m_text                (RX)  : ORIGIN = m_txt_origin, LENGTH = m_itcm_size - m_txt_origin
  m_data                (RW)  : ORIGIN = m_dtcm_base, LENGTH = m_dtcm_size - 4 /* double tap */
  m_data2               (RW)  : ORIGIN = m_ocram_base, LENGTH = m_ocram_size /* ocram */
}
