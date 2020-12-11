/* Specify the memory areas */
MEMORY
{
  m_flash_config        (RX)  : ORIGIN = m_flash_config_origin, LENGTH = 0x00000C00
  m_ivt                 (RX)  : ORIGIN = m_flash_base + 0x1000, LENGTH = 0x00001000
  m_interrupts          (RX)  : ORIGIN = m_flash_base + 0x2000, LENGTH = 0x00000400
  m_text                (RX)  : ORIGIN = m_flash_base + 0x2400, LENGTH = 0xC000 - 0x2400
  m_data                (RW)  : ORIGIN = 0x20000000, LENGTH = m_data_length - 4 /* double tap */
  m_data2               (RW)  : ORIGIN = 0x20200000, LENGTH = 0x00010000
}
