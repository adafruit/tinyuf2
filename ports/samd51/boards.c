#include "board_api.h"

#ifndef BUILD_NO_TINYUSB
  #include "tusb.h"
#endif

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM
//--------------------------------------------------------------------+

#define SAMD51_UID_WORD0 ((volatile uint32_t *)0x008061FC)
#define SAMD51_UID_WORD1 ((volatile uint32_t *)0x00806010)
#define SAMD51_UID_WORD2 ((volatile uint32_t *)0x00806014)
#define SAMD51_UID_WORD3 ((volatile uint32_t *)0x00806018)

// BOD33 level: 1.5V + LEVEL * 6mV = 2.7V
#define BOD33_LEVEL 200

#define USB_DM_PIN  24
#define USB_DP_PIN  25

//--------------------------------------------------------------------+
// Internal Helper
//--------------------------------------------------------------------+

static inline void pin_output(uint8_t port, uint8_t pin, bool high) {
  if (high) {
    PORT->Group[port].OUTSET.reg = 1u << pin;
  } else {
    PORT->Group[port].OUTCLR.reg = 1u << pin;
  }
  PORT->Group[port].DIRSET.reg = 1u << pin;
}

static void dwt_enable(void) {
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

static void delay_ms(uint32_t ms) {
  const uint32_t start  = DWT->CYCCNT;
  const uint32_t cycles = (SystemCoreClock / 1000) * ms;
  while ((DWT->CYCCNT - start) < cycles) {}
}

// The default 1.7V level is too low: flash writes intermittently store zeros
static void bod33_init(void) {
  SUPC->BOD33.bit.ENABLE = 0;
  while (!SUPC->STATUS.bit.B33SRDY) {}
  SUPC->BOD33.bit.LEVEL    = BOD33_LEVEL;
  SUPC->BOD33.bit.ACTION   = SUPC_BOD33_ACTION_NONE_Val;
  SUPC->BOD33.bit.RUNSTDBY = 1;
  SUPC->BOD33.bit.ENABLE   = 1;

  while (!SUPC->STATUS.bit.BOD33RDY) {}
  while (SUPC->STATUS.bit.BOD33DET) {}

  if (RSTC->RCAUSE.bit.POR || RSTC->RCAUSE.bit.BODVDD) {
    do {
      delay_ms(100);
    } while (SUPC->STATUS.bit.BOD33DET);
  }

  SUPC->BOD33.bit.ENABLE = 0;
  while (!SUPC->STATUS.bit.B33SRDY) {}
  SUPC->BOD33.bit.ACTION = SUPC_BOD33_ACTION_RESET_Val;
  SUPC->BOD33.bit.ENABLE = 1;
}

// 48MHz DFLL in USB clock recovery mode, locks to the host SOF so no crystal is needed
static void clock_init(void) {
  NVMCTRL->CTRLA.bit.AUTOWS = 1;

  GCLK->CTRLA.bit.SWRST = 1;
  while (GCLK->SYNCBUSY.bit.SWRST) {}

  // run from the ultra low power 32k oscillator while the DFLL is reconfigured
  GCLK->GENCTRL[0].reg = GCLK_GENCTRL_SRC(GCLK_GENCTRL_SRC_OSCULP32K) | GCLK_GENCTRL_OE | GCLK_GENCTRL_GENEN;
  while (GCLK->SYNCBUSY.bit.GENCTRL0) {}

  OSCCTRL->DFLLCTRLA.reg = 0;

  OSCCTRL->DFLLMUL.reg = OSCCTRL_DFLLMUL_CSTEP(0x1) | OSCCTRL_DFLLMUL_FSTEP(0x1) | OSCCTRL_DFLLMUL_MUL(0xBB80);
  while (OSCCTRL->DFLLSYNC.bit.DFLLMUL) {}

  OSCCTRL->DFLLCTRLB.reg = 0;
  while (OSCCTRL->DFLLSYNC.bit.DFLLCTRLB) {}

  OSCCTRL->DFLLCTRLA.bit.ENABLE = true;
  while (OSCCTRL->DFLLSYNC.bit.ENABLE) {}

  OSCCTRL->DFLLVAL.reg = OSCCTRL->DFLLVAL.reg;
  while (OSCCTRL->DFLLSYNC.bit.DFLLVAL) {}

  OSCCTRL->DFLLCTRLB.reg = OSCCTRL_DFLLCTRLB_WAITLOCK | OSCCTRL_DFLLCTRLB_CCDIS | OSCCTRL_DFLLCTRLB_USBCRM;
  while (!OSCCTRL->STATUS.bit.DFLLRDY) {}

  GCLK->GENCTRL[0].reg =
    GCLK_GENCTRL_SRC(GCLK_GENCTRL_SRC_DFLL) | GCLK_GENCTRL_IDC | GCLK_GENCTRL_OE | GCLK_GENCTRL_GENEN;
  while (GCLK->SYNCBUSY.bit.GENCTRL0) {}

  MCLK->CPUDIV.reg = MCLK_CPUDIV_DIV_DIV1;
}

//--------------------------------------------------------------------+
// Board API
//--------------------------------------------------------------------+

// Only touches what the application can inherit: the clocks stay at their reset
// state until the bootloader decides to stay (board_dfu_init)
void board_init(void) {
  WDT->CTRLA.reg = 0;
  while (WDT->SYNCBUSY.reg) {}

  dwt_enable();
  bod33_init();

  pin_output(NEOPIXEL_POWER_PORT, NEOPIXEL_POWER_PIN, NEOPIXEL_POWER_STATE);
  pin_output(NEOPIXEL_PORT, NEOPIXEL_PIN, false);

  PORT->Group[BUTTON_PORT].PINCFG[BUTTON_PIN].reg = PORT_PINCFG_INEN | PORT_PINCFG_PULLEN;
  PORT->Group[BUTTON_PORT].DIRCLR.reg             = 1u << BUTTON_PIN;
  PORT->Group[BUTTON_PORT].OUTSET.reg             = 1u << BUTTON_PIN;
}

void board_dfu_init(void) {
  clock_init();

  PORT->Group[0].PINCFG[USB_DM_PIN].bit.PMUXEN = 1;
  PORT->Group[0].PINCFG[USB_DP_PIN].bit.PMUXEN = 1;
  PORT->Group[0].PMUX[USB_DM_PIN / 2].reg      = PORT_PMUX_PMUXE(MUX_PA24H_USB_DM) | PORT_PMUX_PMUXO(MUX_PA25H_USB_DP);

  MCLK->AHBMASK.reg |= MCLK_AHBMASK_USB;
  MCLK->APBBMASK.reg |= MCLK_APBBMASK_USB;
  GCLK->PCHCTRL[USB_GCLK_ID].reg = GCLK_PCHCTRL_GEN_GCLK0 | GCLK_PCHCTRL_CHEN;
}

void board_reset(void) {
  NVIC_SystemReset();
}

void board_dfu_complete(void) {
  NVIC_SystemReset();
}

// Holding the button at reset forces the bootloader. The line rises slowly after power-up
bool board_app_valid2(void) {
  delay_ms(20);
  const bool pressed = ((PORT->Group[BUTTON_PORT].IN.reg >> BUTTON_PIN) & 1u) == BUTTON_STATE_ACTIVE;
  return !pressed;
}

bool board_app_valid(void) {
  const volatile uint32_t *app_vector = (const volatile uint32_t *)BOARD_FLASH_APP_START;
  const uint32_t           sp         = app_vector[0];
  const uint32_t           app_entry  = app_vector[1];

  TUF2_LOG1_HEX(sp);
  TUF2_LOG1_HEX(app_entry);

  // 1st word is stack pointer (must be in SRAM region)
  if ((sp & 0xff000003) != 0x20000000) {
    return false;
  }

  // 2nd word is app entry point (reset)
  if (app_entry < BOARD_FLASH_APP_START || app_entry > BOARD_FLASH_ADDR_ZERO + BOARD_FLASH_SIZE) {
    return false;
  }

  return true;
}

void board_teardown(void) {
  PORT->Group[BUTTON_PORT].PINCFG[BUTTON_PIN].reg = 0;
  PORT->Group[BUTTON_PORT].OUTCLR.reg             = 1u << BUTTON_PIN;

  SysTick->CTRL = 0;
  SysTick->LOAD = 0;
  SysTick->VAL  = 0;
}

void board_app_jump(void) {
  const volatile uint32_t *app_vector = (const volatile uint32_t *)BOARD_FLASH_APP_START;
  const uint32_t           sp         = app_vector[0];
  const uint32_t           app_entry  = app_vector[1];

  for (uint8_t i = 0; i < sizeof(NVIC->ICER) / sizeof(NVIC->ICER[0]); i++) {
    NVIC->ICER[i] = 0xFFFFFFFFu;
  }

  SCB->VTOR = BOARD_FLASH_APP_START;

  __set_MSP(sp);
  __set_PSP(sp);

  asm("bx %0" ::"r"(app_entry));
}

uint8_t board_usb_get_serial(uint8_t serial_id[16]) {
  uint32_t *serial_id32 = (uint32_t *)(uintptr_t)serial_id;

  serial_id32[0] = *SAMD51_UID_WORD0;
  serial_id32[1] = *SAMD51_UID_WORD1;
  serial_id32[2] = *SAMD51_UID_WORD2;
  serial_id32[3] = *SAMD51_UID_WORD3;

  return 16;
}

//--------------------------------------------------------------------+
// LED pattern
//--------------------------------------------------------------------+

void board_led_write(uint32_t state) {
  (void)state;
}

static inline uint8_t apply_percentage(uint8_t brightness) {
  return (uint8_t)((brightness * NEOPIXEL_BRIGHTNESS) >> 8);
}

// The strip reads a pulse as a 1 once it is high for about 0.5us. The counts include the fixed cost of the PORT
// writes and cycle counter reads, they are tuned for a 48MHz core and give ~0.3us/0.6us high and ~1.2us per bit.
#define NEOPIXEL_T0H_CYCLES 4
#define NEOPIXEL_T1H_CYCLES 25
#define NEOPIXEL_BIT_CYCLES 36
#define NEOPIXEL_RESET_NS   80000

static uint32_t ns_to_cycles(uint32_t ns) {
  return (SystemCoreClock / 1000000) * ns / 1000;
}

// Runs from RAM, so the pulse widths do not depend on flash wait states or the NVM cache
static __attribute__((section(".ramfunc"), noinline)) void neopixel_send(const uint8_t *grb, uint32_t count) {
  for (uint32_t i = 0; i < count; i++) {
    for (uint32_t c = 0; c < 3; c++) {
      for (uint8_t mask = 0x80; mask != 0; mask >>= 1) {
        const uint32_t high  = (grb[c] & mask) ? NEOPIXEL_T1H_CYCLES : NEOPIXEL_T0H_CYCLES;
        const uint32_t start = DWT->CYCCNT;

        PORT->Group[NEOPIXEL_PORT].OUTSET.reg = 1u << NEOPIXEL_PIN;
        while ((DWT->CYCCNT - start) < high) {}

        PORT->Group[NEOPIXEL_PORT].OUTCLR.reg = 1u << NEOPIXEL_PIN;
        while ((DWT->CYCCNT - start) < NEOPIXEL_BIT_CYCLES) {}
      }
    }
  }
}

void board_rgb_write(const uint8_t rgb[]) {
  static uint32_t last_end = 0;

  // neopixel color order is GRB
  const uint8_t grb[3] = {apply_percentage(rgb[1]), apply_percentage(rgb[0]), apply_percentage(rgb[2])};

  // the previous frame is latched once the line has been low for the reset time
  while ((DWT->CYCCNT - last_end) < ns_to_cycles(NEOPIXEL_RESET_NS)) {}

  const uint32_t primask = __get_PRIMASK();
  __disable_irq();
  neopixel_send(grb, NEOPIXEL_NUMBER);
  __set_PRIMASK(primask);

  last_end = DWT->CYCCNT;
}

//--------------------------------------------------------------------+
// Timer
//--------------------------------------------------------------------+
void board_timer_start(uint32_t ms) {
  SysTick_Config((SystemCoreClock / 1000) * ms);
}

void board_timer_stop(void) {
  SysTick->CTRL &= ~SysTick_CTRL_ENABLE_Msk;
}

void SysTick_Handler(void) {
  board_timer_handler();
}

int board_uart_write(const void *buf, int len) {
  (void)buf;
  (void)len;
  return 0;
}

#ifndef BUILD_NO_TINYUSB
void USB_0_Handler(void) {
  tud_int_handler(0);
}
void USB_1_Handler(void) {
  tud_int_handler(0);
}
void USB_2_Handler(void) {
  tud_int_handler(0);
}
void USB_3_Handler(void) {
  tud_int_handler(0);
}
#endif
