/* Specify the memory areas */
MEMORY
{
  m_flash_config        (RX)  : ORIGIN = m_ocram_rom_safe_origin, LENGTH = 0x00000C00 /* fcfb */
  m_ivt                 (RX)  : ORIGIN = m_ocram_rom_safe_origin + 0x0C00, LENGTH = 0x00000400
  m_interrupts          (RX)  : ORIGIN = m_ocram_rom_safe_origin + 0x1000, LENGTH = 0x00000400
  m_text                (RX)  : ORIGIN = m_ocram_rom_safe_origin + 0x1400, LENGTH = 0x00009000
  m_data                (RW)  : ORIGIN = 0x20000000, LENGTH = m_data_length - 4 /* double tap */
  m_data2               (RW)  : ORIGIN = 0x00000000, LENGTH = 0x00008000 /* itcm */
}
