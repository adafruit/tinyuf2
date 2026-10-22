// The HIL's board facts as the bootloader's own compile sees them (hil-contract Build): check_build compiles this
// with the compile command of the tinyuf2 target's src/main.c and never links it; board_facts.py reads each hil_*
// object, a link-time address as its relocation against the bootloader ELF's symbol.
#include <stdint.h>
#include "board_api.h"

#define HIL_STR(x) #x
#define HIL_XSTR(x) HIL_STR(x)

const uint32_t hil_flash_addr_zero = (uint32_t) (BOARD_FLASH_ADDR_ZERO);
const uint32_t hil_flash_app_start = (uint32_t) (BOARD_FLASH_APP_START);
// a runtime read (CMSIS FLASH_SIZE, the chip's size register) is no constant: hil_flash_size_expr then says which
const uint32_t hil_flash_size_constant = __builtin_constant_p(BOARD_FLASH_SIZE);
const uint32_t hil_flash_size = __builtin_constant_p(BOARD_FLASH_SIZE) ? (uint32_t) (BOARD_FLASH_SIZE) : 0;
const uint32_t hil_usb_vid = USB_VID;
const uint32_t hil_usb_pid = USB_PID;
const char hil_board_id[] = UF2_BOARD_ID;
const uint32_t hil_family = BOARD_UF2_FAMILY_ID;
const uint32_t hil_dbl_tap_delay = TINYUF2_DBL_TAP_DELAY;
const uint32_t hil_dbl_tap_size = TINYUF2_DBL_TAP_REG_SIZE;
const uint32_t hil_dbl_tap_magic = DBL_TAP_MAGIC;
const uint32_t hil_dbl_tap_reg = (uint32_t) (uintptr_t) &TINYUF2_DBL_TAP_REG;
#if defined(NUMBER_OF_INT_VECTORS)
const uint32_t hil_vectors = NUMBER_OF_INT_VECTORS;
#elif defined(MXC_IRQ_COUNT)
const uint32_t hil_vectors = MXC_IRQ_COUNT;
#endif

// last: BOARD_FLASH_SIZE's expansion with FLASH_SIZE left unexpanded, its exact tokens
#if defined(FLASH_SIZE)
#undef FLASH_SIZE
const char hil_flash_size_expr[] = HIL_XSTR(BOARD_FLASH_SIZE);
#endif
