/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2018 Ha Thach for Adafruit Industries
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 *
 */

#include "board_api.h"

#include "fsl_gpio.h"
#include "fsl_iomuxc.h"
#include "fsl_clock.h"
#include "fsl_ocotp.h"
#include "fsl_lpuart.h"
#include "fsl_pwm.h"
#include "fsl_xbara.h"

#include "clock_config.h"

#ifndef BUILD_NO_TINYUSB
#include "tusb.h"
#endif

static bool _dfu_mode = false;

// needed by fsl_flexspi_nor_boot
const uint8_t dcd_data[] = { 0x00 };

void board_init(void)
{
#if defined(__DCACHE_PRESENT) && __DCACHE_PRESENT
  if (SCB_CCR_DC_Msk != (SCB_CCR_DC_Msk & SCB->CCR)) SCB_EnableDCache();
#endif

  // Init clock
  BOARD_BootClockRUN();

  // TODO System clock update could cause incorrect neopixel timing, make sure it right later
  // SystemCoreClockUpdate();

  board_timer_stop();

  // Enable IOCON clock
  CLOCK_EnableClock(kCLOCK_Iomuxc);

  // Prevent clearing of SNVS General Purpose Register
  SNVS->LPCR |= SNVS_LPCR_GPR_Z_DIS_MASK;

#ifdef LED_PINMUX
  IOMUXC_SetPinMux(LED_PINMUX, 0);
  IOMUXC_SetPinConfig(LED_PINMUX, 0x10B0U);

  gpio_pin_config_t led_config = { kGPIO_DigitalOutput, 0, kGPIO_NoIntmode };
  GPIO_PinInit(LED_PORT, LED_PIN, &led_config);
#endif

#if NEOPIXEL_NUMBER
  IOMUXC_SetPinMux(NEOPIXEL_PINMUX, 0);
  IOMUXC_SetPinConfig(NEOPIXEL_PINMUX, 0x10B0U);

  gpio_pin_config_t neopixel_config = { kGPIO_DigitalOutput, 0, kGPIO_NoIntmode };
  GPIO_PinInit(NEOPIXEL_PORT, NEOPIXEL_PIN, &neopixel_config);
#endif

#if TUF2_LOG
  board_uart_init(BOARD_UART_BAUDRATE);
#endif
}

void board_teardown(void)
{
  // no GPIO deinit for GPIO: LED, Neopixel, Button
#if TUF2_LOG && defined(UART_DEV)
  LPUART_Deinit(UART_DEV);
#endif
}

void board_usb_init(void)
{
  USBPHY_Type* usb_phy;

#if BOARD_TUD_RHPORT == 0
  // Clock
  CLOCK_EnableUsbhs0PhyPllClock(kCLOCK_Usbphy480M, 480000000U);
  CLOCK_EnableUsbhs0Clock(kCLOCK_Usb480M, 480000000U);

  #ifdef USBPHY1
  usb_phy = USBPHY1;
  #else
  usb_phy = USBPHY;
  #endif

#elif BOARD_TUD_RHPORT == 1
  // USB1
  CLOCK_EnableUsbhs1PhyPllClock(kCLOCK_Usbphy480M, 480000000U);
  CLOCK_EnableUsbhs1Clock(kCLOCK_Usb480M, 480000000U);
  usb_phy = USBPHY2;
#endif

  // Enable PHY support for Low speed device + LS via FS Hub
  usb_phy->CTRL |= USBPHY_CTRL_SET_ENUTMILEVEL2_MASK | USBPHY_CTRL_SET_ENUTMILEVEL3_MASK;

  // Enable all power for normal operation
  usb_phy->PWD = 0;

  // TX Timing
  uint32_t phytx = usb_phy->TX;
  phytx &= ~(USBPHY_TX_D_CAL_MASK | USBPHY_TX_TXCAL45DM_MASK | USBPHY_TX_TXCAL45DP_MASK);
  phytx |= USBPHY_TX_D_CAL(0x0C) | USBPHY_TX_TXCAL45DP(0x06) | USBPHY_TX_TXCAL45DM(0x06);
  usb_phy->TX = phytx;
}

void board_dfu_init(void)
{
  board_usb_init();

  _dfu_mode = true;

#ifdef LED_PWM_PINMUX
  IOMUXC_SetPinMux(LED_PWM_PINMUX, 0);
  IOMUXC_SetPinConfig(LED_PWM_PINMUX, 0x10B0U);

  CLOCK_SetDiv(kCLOCK_AhbDiv, 0x2); /* Set AHB PODF to 2, divide by 3 */
  CLOCK_SetDiv(kCLOCK_IpgDiv, 0x3); /* Set IPG PODF to 3, divide by 4 */
  SystemCoreClockUpdate();

  XBARA_Init(XBARA);
  XBARA_SetSignalsConnection(XBARA, kXBARA1_InputLogicHigh, kXBARA1_OutputFlexpwm1Fault0);
  XBARA_SetSignalsConnection(XBARA, kXBARA1_InputLogicHigh, kXBARA1_OutputFlexpwm1Fault1);
  XBARA_SetSignalsConnection(XBARA, kXBARA1_InputLogicHigh, kXBARA1_OutputFlexpwm1Fault2);
  XBARA_SetSignalsConnection(XBARA, kXBARA1_InputLogicHigh, kXBARA1_OutputFlexpwm1Fault3);

  pwm_config_t pwmConfig;
  PWM_GetDefaultConfig(&pwmConfig);

  PWM_Init(LED_PWM_BASE, LED_PWM_MODULE, &pwmConfig);

  pwm_signal_param_t pwmSignal =
  {
    .pwmChannel       = LED_PWM_CHANNEL,
    .dutyCyclePercent = 0,
    .level            = LED_STATE_ON ? kPWM_HighTrue : kPWM_LowTrue,
    .deadtimeValue    = 0,
    .faultState       = kPWM_PwmFaultState0
  };
  PWM_SetupPwm(LED_PWM_BASE, LED_PWM_MODULE, &pwmSignal, 1, kPWM_SignedCenterAligned, 5000, CLOCK_GetFreq(kCLOCK_IpgClk));

  PWM_SetPwmLdok(LED_PWM_BASE, 1 << LED_PWM_MODULE, true);
  PWM_StartTimer(LED_PWM_BASE, 1 << LED_PWM_MODULE);
#endif
}

uint8_t board_usb_get_serial(uint8_t serial_id[16])
{
  #if FSL_FEATURE_OCOTP_HAS_TIMING_CTRL
  OCOTP_Init(OCOTP, CLOCK_GetFreq(kCLOCK_IpgClk));
  #else
  OCOTP_Init(OCOTP, 0u);
  #endif

  // Reads shadow registers 0x01 - 0x04 (Configuration and Manufacturing Info)
  // into 8 bit wide destination, avoiding punning.
  for (int i = 0; i < 4; ++i) {
    uint32_t wr = OCOTP_ReadFuseShadowRegister(OCOTP, i + 1);
    for (int j = 0; j < 4; j++) {
      serial_id[i*4+j] = wr & 0xff;
      wr >>= 8;
    }
  }
  OCOTP_Deinit(OCOTP);

  return 16;
}

void board_reset(void)
{
  NVIC_SystemReset();
}

void board_dfu_complete(void)
{
  NVIC_SystemReset();
}

bool board_app_valid(void)
{
  volatile uint32_t const * app_vector = (volatile uint32_t const*) BOARD_FLASH_APP_START;

  // 1st word is stack pointer (should be in SRAM region)

  // 2nd word is App entry point (reset)
  if (app_vector[1] < BOARD_FLASH_APP_START || app_vector[1] > BOARD_FLASH_APP_START + BOARD_FLASH_SIZE) {
    return false;
  }

  return true;
}

void board_app_jump(void)
{
  // Create the function call to the user application.
  // Static variables are needed since changed the stack pointer out from under the compiler
  // we need to ensure the values we are using are not stored on the previous stack
  static uint32_t stack_pointer;
  static uint32_t app_entry;

  uint32_t const * app_vector = (uint32_t const*) BOARD_FLASH_APP_START;
  stack_pointer = app_vector[0];
  app_entry = app_vector[1];

  // TODO protect bootloader region

  /* switch exception handlers to the application */
  SCB->VTOR = (uint32_t) BOARD_FLASH_APP_START;

  // Set stack pointer
  __set_MSP(stack_pointer);
  __set_PSP(stack_pointer);

  // Jump to Application Entry
  asm("bx %0" ::"r"(app_entry));
}

//--------------------------------------------------------------------+
// Timer
//--------------------------------------------------------------------+

void board_timer_start(uint32_t ms)
{
  // due to highspeed SystemCoreClock = 600 mhz, max interval of 24 bit systick is only 27 ms
  const uint32_t tick = (SystemCoreClock/1000) * ms;
  SysTick_Config( tick );
}

void board_timer_stop(void)
{
  SysTick->CTRL = 0;
}

void SysTick_Handler(void)
{
  board_timer_handler();
}

//--------------------------------------------------------------------+
// LED / RGB
//--------------------------------------------------------------------+

void board_led_write(uint32_t value)
{
#ifdef LED_PINMUX
#ifdef LED_PWM_PINMUX
  if (_dfu_mode)
  {
    uint8_t duty = (value * 100) / 0xff;
    PWM_UpdatePwmDutycycle(LED_PWM_BASE, LED_PWM_MODULE, LED_PWM_CHANNEL, kPWM_SignedCenterAligned, duty);
    PWM_SetPwmLdok(LED_PWM_BASE, 1 << LED_PWM_MODULE, true);
  }else
#endif
  {
    value = (value >= 128) ? 1 : 0;
    GPIO_PinWrite(LED_PORT, LED_PIN, value ? LED_STATE_ON : (1-LED_STATE_ON));
  }
#endif
}

#if NEOPIXEL_NUMBER
#define MAGIC_800_INT   900000  // ~1.11 us -> 1.2  field
#define MAGIC_800_T0H  2800000  // ~0.36 us -> 0.44 field
#define MAGIC_800_T1H  1350000  // ~0.74 us -> 0.84 field

static inline uint8_t apply_percentage(uint8_t brightness)
{
  return (uint8_t) ((brightness*NEOPIXEL_BRIGHTNESS) >> 8);
}

void board_rgb_write(uint8_t const rgb[])
{
  enum {
    PIN_MASK = (1u << NEOPIXEL_PIN)
  };

  // neopixel color order is GRB
  uint8_t const pixels[3] = { apply_percentage(rgb[1]), apply_percentage(rgb[0]), apply_percentage(rgb[2]) };
  uint32_t const numBytes = 3;

  uint8_t const *p = pixels, *end = p + numBytes;
  uint8_t pix = *p++, mask = 0x80;
  uint32_t start = 0;
  uint32_t cyc = 0;

  //assumes 800_000Hz frequency
  //Theoretical values here are 800_000 -> 1.25us, 2500000->0.4us, 1250000->0.8us
  //TODO: try to get dynamic weighting working again
  uint32_t const sys_freq = SystemCoreClock;
  uint32_t const interval = sys_freq/MAGIC_800_INT;
  uint32_t const t0       = sys_freq/MAGIC_800_T0H;
  uint32_t const t1       = sys_freq/MAGIC_800_T1H;

  volatile uint32_t* reg_set = &NEOPIXEL_PORT->DR_SET;
  volatile uint32_t* reg_clr = &NEOPIXEL_PORT->DR_CLEAR;

  __disable_irq();

  // Enable DWT in debug core. Usable when interrupts disabled, as opposed to Systick->VAL
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
  DWT->CYCCNT = 0;

  while(1) {
    cyc = (pix & mask) ? t1 : t0;
    while((DWT->CYCCNT - start) < interval);

    start = DWT->CYCCNT;

    *reg_set = PIN_MASK;
    while((DWT->CYCCNT - start) < cyc);

    *reg_clr = PIN_MASK;

    if(!(mask >>= 1)) {
      if(p >= end) break;
      pix  = *p++;
      mask = 0x80;
    }
  }

  __enable_irq();
}

#else

void board_rgb_write(uint8_t const rgb[])
{
  (void) rgb;
}

#endif

//--------------------------------------------------------------------+
// UART
//--------------------------------------------------------------------+

#ifdef UART_DEV
void board_uart_init(uint32_t baud_rate)
{
  // Enable UART when debug log is on
  IOMUXC_SetPinMux(UART_RX_PINMUX, 0);
  IOMUXC_SetPinMux(UART_TX_PINMUX, 0);

  IOMUXC_SetPinConfig(UART_RX_PINMUX, 0x10A0U);
  IOMUXC_SetPinConfig(UART_TX_PINMUX, 0x10A0U);

  lpuart_config_t uart_config;
  LPUART_GetDefaultConfig(&uart_config);
  uart_config.baudRate_Bps = baud_rate;
  uart_config.enableTx = true;
  uart_config.enableRx = true;

  uint32_t freq;
  if (CLOCK_GetMux(kCLOCK_UartMux) == 0) /* PLL3 div6 80M */
  {
    freq = (CLOCK_GetPllFreq(kCLOCK_PllUsb1) / 6U) / (CLOCK_GetDiv(kCLOCK_UartDiv) + 1U);
  }
  else
  {
    freq = CLOCK_GetOscFreq() / (CLOCK_GetDiv(kCLOCK_UartDiv) + 1U);
  }

  LPUART_Init(UART_DEV, &uart_config, freq);
}

int board_uart_write(void const * buf, int len)
{
  LPUART_WriteBlocking(UART_DEV, (uint8_t const*) buf, (size_t) len);
  return len;
}

// optional API, not included in board_api.h
int board_uart_read(uint8_t* buf, int len)
{
  int count = 0;

  while( count < len )
  {
    uint8_t const rx_count = LPUART_GetRxFifoCount(UART_DEV);
    if (!rx_count)
    {
      // clear all error flag if any
      uint32_t status_flags = LPUART_GetStatusFlags(UART_DEV);
      status_flags  &= (kLPUART_RxOverrunFlag | kLPUART_ParityErrorFlag | kLPUART_FramingErrorFlag | kLPUART_NoiseErrorFlag);
      LPUART_ClearStatusFlags(UART_DEV, status_flags);
      break;
    }

    for(int i=0; i<rx_count; i++)
    {
      buf[count] = LPUART_ReadByte(UART_DEV);
      count++;
    }
  }

  return count;
}

#else

void board_uart_init(uint32_t baud_rate) {
  (void) baud_rate;
}

int board_uart_write(void const * buf, int len) {
  (void) buf; (void) len;
  return 0;
}

int board_uart_read(uint8_t* buf, int len) {
  (void) buf; (void) len;
  return 0;
}
#endif


//--------------------------------------------------------------------+
// USB Interrupt Handler
//--------------------------------------------------------------------+
#ifndef BUILD_NO_TINYUSB

// The iMX RT 1040 is named without a number. We can always have this because
// it'll get GC'd when not used.
void USB_OTG_IRQHandler(void) {
  tud_int_handler(0);
}

void USB_OTG1_IRQHandler(void) {
  tud_int_handler(0);
}

void USB_OTG2_IRQHandler(void) {
  tud_int_handler(1);
}

#endif
