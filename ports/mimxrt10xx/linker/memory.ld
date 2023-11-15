/* fcfb */
_fcfb_length = _ivt_origin - _fcfb_origin;

/* ivt */
_ivt_flash_offset = 0x1000; /* The location of the ivt in flash. */
_ivt_length = 0x0400;

/* interrupt */
_interrupts_origin = _ivt_origin + _ivt_length;
_interrupts_length = 0x0400;

/* text */
_text_origin = _interrupts_origin + _interrupts_length;
_text_length = 0x8800;

/* The image starts at the first flash address so our full boot length includes
   the ivt offset plus our data lengths. */
_board_boot_length = _ivt_flash_offset + _ivt_length + _interrupts_length + _text_length;

ASSERT(_board_boot_length <= 0xC000, "Bootloader too big. Runs into user app.")

/* Specify the memory areas */
MEMORY
{
  m_flash_config        (RX)  : ORIGIN = _fcfb_origin       , LENGTH = _fcfb_length
  m_ivt                 (RX)  : ORIGIN = _ivt_origin        , LENGTH = _ivt_length
  m_interrupts          (RX)  : ORIGIN = _interrupts_origin , LENGTH = _interrupts_length
  m_text                (RX)  : ORIGIN = _text_origin       , LENGTH = _text_length

  m_data                (RW)  : ORIGIN = _dtcm_base         , LENGTH = _dtcm_size
  m_data2               (RW)  : ORIGIN = _ocram_base        , LENGTH = _ocram_size
}

/* _fcfb_origin & _ivt_origin are mcu specific and defined by their ld file
 *
 * -------------
 * |   text    |
 * | (0x8800)  |
 * -------------
 * | interrupt |
 * | (0x0400)  |
 * -------------
 * |   ivt     |
 * | (0x0400)  |
 * ------------- _ivt_origin
 * |   fcfb    |
 * |           |
 * ------------- _fcfb_origin
 */
