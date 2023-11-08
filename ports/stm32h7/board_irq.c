#include "board_api.h"
#ifndef BUILD_NO_TINYUSB
#include "tusb.h"
#endif

volatile bool timer_on = false;
volatile uint32_t timer_ms = 0;

#ifndef TINYUF2_SELF_UPDATE

//--------------------------------------------------------------------+
// Core Interrupts
//--------------------------------------------------------------------+

// Forward USB interrupt events to TinyUSB IRQ Handler
// void OTG_HS_EP1_OUT_IRQHandler(void)
// void OTG_HS_EP1_IN_IRQHandler(void)
// void OTG_HS_WKUP_IRQHandler(void)
// void OTG_FS_EP1_OUT_IRQHandler(void)
// void OTG_FS_EP1_IN_IRQHandler(void)
// void OTG_FS_WKUP_IRQHandler(void)

#ifndef BUILD_NO_TINYUSB
void OTG_FS_IRQHandler(void)
{
  tud_int_handler(0);
}

void OTG_HS_IRQHandler(void)
{
  tud_int_handler(1);
}
#endif // BUILD_NO_TINYUSB
#endif // TINYUF2_SELF_UPDATE

//--------------------------------------------------------------------+
// Core Exceptions
//--------------------------------------------------------------------+
void SysTick_Handler(void)
{
  HAL_IncTick();
  board_timer_handler();
}

#if defined(TRAP_EXC)

typedef struct __attribute__((packed)) CtxFrame {
  uint32_t r0;
  uint32_t r1;
  uint32_t r2;
  uint32_t r3;
  uint32_t r12;
  uint32_t lr;
  uint32_t ret;
  uint32_t xpsr;
} sFrame;

#define HARDFAULT_HANDLER(_x) \
  asm volatile("tst lr, #4 \n" \
  "ite eq \n" \
  "mrseq r0, msp \n" \
  "mrsne r0, psp \n" \
  "b fault_handler \n")

#define R ": %lx"
#define EXC_FMT "r0" R "r1" R "r2" R "r3" R "r12" R "lr" R "ret" R "xpsr" R "\n"
#define EXC_DET(x) x->r0, x->r1, x->r2, x->r3, x->r12, x->lr, x->ret, x->xpsr

__attribute__((optimize("O0")))
void fault_handler(sFrame *fr)
{
  TUF2_LOG1(EXC_FMT, EXC_DET(fr));
  asm("bkpt #0");
  (void) fr;
}

void HardFault_Handler(void)
{
  HARDFAULT_HANDLER();
}
#endif // defined(TRAP_EXC)
