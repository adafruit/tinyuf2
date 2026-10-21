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
 */

#include "board_api.h"
#include "fsl_device_registers.h"
#include "fsl_rtc.h"
#include "fsl_iap.h"
#include "fsl_iap_ffr.h"
#include "fsl_gpio.h"
#include "fsl_usart.h"
#include "fsl_power.h"
#include "fsl_iocon.h"
#include "clock_config.h"

#ifndef BUILD_NO_TINYUSB
  #include "tusb.h"
#else
  #define TU_LOG1(...)
  #define TU_LOG2(...)
#endif

#if NEOPIXEL_NUMBER
#include "sct_neopixel.h"
static uint32_t _pixelData[NEOPIXEL_NUMBER] = {0};
#endif

#ifdef LED_TRICOLOR_GPIO
static uint8_t const _led_tricolor[3][2] = LED_TRICOLOR_GPIO;
#endif

//--------------------------------------------------------------------+
// IOCON Defines
//--------------------------------------------------------------------+

#define IOCON_PIO_ASW_DIS_EN     0x00u   /*!<@brief Analog switch is closed (enabled), only for A0 version */
#define IOCON_PIO_ASW_EN         0x0400u /*!<@brief Analog switch is closed (enabled) */
#define IOCON_PIO_DIGITAL_EN     0x0100u /*!<@brief Enables digital function */
#define IOCON_PIO_FUNC0          0x00u   /*!<@brief Selects pin function 0 */
#define IOCON_PIO_FUNC1          0x01u   /*!<@brief Selects pin function 1 */
#define IOCON_PIO_FUNC2          0x02u   /*!<@brief Selects pin function 7 */
#define IOCON_PIO_FUNC3          0x03u   /*!<@brief Selects pin function 0 */
#define IOCON_PIO_FUNC4          0x04u   /*!<@brief Selects pin function 1 */
#define IOCON_PIO_FUNC5          0x05u   /*!<@brief Selects pin function 7 */
#define IOCON_PIO_FUNC6          0x06u   /*!<@brief Selects pin function 7 */
#define IOCON_PIO_FUNC7          0x07u   /*!<@brief Selects pin function 7 */
#define IOCON_PIO_INV_DI         0x00u   /*!<@brief Input function is not inverted */
#define IOCON_PIO_MODE_INACT     0x00u   /*!<@brief No addition pin function */
#define IOCON_PIO_MODE_PULLUP    0x20u   /*!<@brief Selects pull-up function */
#define IOCON_PIO_OPENDRAIN_DI   0x00u   /*!<@brief Open drain is disabled */
#define IOCON_PIO_SLEW_STANDARD  0x00u   /*!<@brief Standard mode, output slew rate control is enabled */

#define IOCON_PIO_DIG_FUNC0_EN   (IOCON_PIO_DIGITAL_EN | IOCON_PIO_FUNC0) /*!<@brief Digital pin function 0 enabled */
#define IOCON_PIO_DIG_FUNC1_EN   (IOCON_PIO_DIGITAL_EN | IOCON_PIO_FUNC1) /*!<@brief Digital pin function 1 enabled */
#define IOCON_PIO_DIG_FUNC2_EN   (IOCON_PIO_DIGITAL_EN | IOCON_PIO_FUNC2) /*!<@brief Digital pin function 2 enabled */
#define IOCON_PIO_DIG_FUNC3_EN   (IOCON_PIO_DIGITAL_EN | IOCON_PIO_FUNC3) /*!<@brief Digital pin function 0 enabled */
#define IOCON_PIO_DIG_FUNC4_EN   (IOCON_PIO_DIGITAL_EN | IOCON_PIO_FUNC4) /*!<@brief Digital pin function 1 enabled */
#define IOCON_PIO_DIG_FUNC5_EN   (IOCON_PIO_DIGITAL_EN | IOCON_PIO_FUNC5) /*!<@brief Digital pin function 2 enabled */
#define IOCON_PIO_DIG_FUNC6_EN   (IOCON_PIO_DIGITAL_EN | IOCON_PIO_FUNC6) /*!<@brief Digital pin function 2 enabled */
#define IOCON_PIO_DIG_FUNC7_EN   (IOCON_PIO_DIGITAL_EN | IOCON_PIO_FUNC7) /*!<@brief Digital pin function 2 enabled */

//--------------------------------------------------------------------+
// MACRO TYPEDEF CONSTANT ENUM DECLARATION
//--------------------------------------------------------------------+

#define IOCON_VBUS_CONFIG        IOCON_PIO_DIG_FUNC7_EN /*!<@brief Digital pin function 7 enabled */

// FLASH
#define NO_CACHE        0xffffffff

#define FLASH_PAGE_SIZE 512
#define FLASH_WORD_SIZE 16 // ECC unit: reading an erased word fails with an ECC error
#define FILESYSTEM_BLOCK_SIZE 256

static flash_config_t _flash_config;
static uint32_t _flash_page_addr = NO_CACHE;
static uint8_t  _flash_cache[FLASH_PAGE_SIZE] __attribute__((aligned(4)));

//--------------------------------------------------------------------+
//
//--------------------------------------------------------------------+

void board_flash_init(void)
{
}

uint32_t board_flash_size(void)
{
  return BOARD_FLASH_SIZE;
}

void board_flash_read(uint32_t addr, void* buffer, uint32_t len)
{
  FLASH_Read(&_flash_config, addr, buffer, len);
}

// Not FLASH_VerifyProgram(): on a mismatch the revision 0A ROM re-reads the same chunk forever (#500)
static bool flash_page_matches_cache(void)
{
  uint8_t buf[FLASH_WORD_SIZE];

  for (uint32_t offset = 0; offset < FLASH_PAGE_SIZE; offset += sizeof(buf)) {
    if (FLASH_Read(&_flash_config, _flash_page_addr + offset, buf, sizeof(buf)) != kStatus_Success ||
        memcmp(buf, _flash_cache + offset, sizeof(buf)) != 0) {
      return false;
    }
  }

  return true;
}

void board_flash_flush(void)
{
  if ( _flash_page_addr == NO_CACHE ) return;

  if (!flash_page_matches_cache()) {
    TU_LOG1("Erase and Write at address = 0x%08lX\r\n",_flash_page_addr);
    FLASH_Erase(&_flash_config, _flash_page_addr, FLASH_PAGE_SIZE, kFLASH_ApiEraseKey);
    FLASH_Program(&_flash_config, _flash_page_addr, _flash_cache, FLASH_PAGE_SIZE);
  }

  _flash_page_addr = NO_CACHE;
}

bool board_flash_write(uint32_t addr, void const* data, uint32_t len)
{
  uint32_t newAddr = addr & ~(FLASH_PAGE_SIZE - 1);

  if (newAddr != _flash_page_addr) {
    board_flash_flush();
    _flash_page_addr = newAddr;
    // per word: a failed read leaves the cache holding the previous page's bytes
    for (uint32_t offset = 0; offset < FLASH_PAGE_SIZE; offset += FLASH_WORD_SIZE) {
      if (FLASH_Read(&_flash_config, newAddr + offset, _flash_cache + offset, FLASH_WORD_SIZE) != kStatus_Success) {
        memset(_flash_cache + offset, 0xFF, FLASH_WORD_SIZE);
      }
    }
  }
  memcpy(_flash_cache + (addr & (FLASH_PAGE_SIZE - 1)), data, len);

  return true;
}

void board_flash_erase_app(void)
{
  // TODO implement later
}

bool board_flash_protect_bootloader(bool protect)
{
  // TODO implement later
  (void) protect;
  return false;
}

uint8_t board_usb_get_serial(uint8_t serial_id[16])
{
  FFR_GetUUID(&_flash_config, serial_id);
  return 16;
}

// Check if application is valid
bool board_app_valid(void)
{
  uint32_t readData[2];
  status_t readStatus;

  // 2nd word is App entry point (reset)
  readStatus = FLASH_Read(&_flash_config, BOARD_FLASH_APP_START, (uint8_t *)readData, 8);
  if (readStatus) {
    if (readStatus == kStatus_FLASH_EccError){
      TU_LOG1("No app present (erased)\r\n");  // Erased flash causes ECC errors
    } else {
      TU_LOG1("Flash read failed status: %ld, \r\n", readStatus);
    }
    return false;
  } else {
    if ((readData[1] >= BOARD_FLASH_APP_START) && (readData[1] < BOARD_FLASH_SIZE)) {
      TU_LOG2("Valid reset vector:  0x%08lX\r\n", readData[1]);
      return true;
    } else {
      TU_LOG1("No app present (invalid vector)\r\n");
      return false;
    }
  }
}

void board_init(void)
{
  // Enable IOCON clock
  CLOCK_EnableClock(kCLOCK_Iocon);

  // Init 96 MHz clock
  BOARD_BootClockFROHF96M();

  // Init RTC for access to TINYUF2_DBL_TAP_REG
  RTC_Init(RTC);

  // disable systick
  board_timer_stop();

  // Initialize Pins
  GPIO_PortInit(GPIO, 0);
  GPIO_PortInit(GPIO, 1);

  // GPIO_PinInit(GPIO, BUTTON_PORT, BUTTON_PIN, &(gpio_pin_config_t){kGPIO_DigitalInput, 0});

#ifdef LED_PIN
  IOCON_PinMuxSet(IOCON, LED_PORT, LED_PIN, IOCON_PIO_DIG_FUNC0_EN);
  GPIO_PinInit(GPIO, LED_PORT, LED_PIN, &(gpio_pin_config_t){kGPIO_DigitalOutput, 1-LED_STATE_ON});
#endif

#ifdef LED_TRICOLOR_GPIO
  for(uint8_t i=0; i<3; i++)
  {
    IOCON_PinMuxSet(IOCON, _led_tricolor[i][0], _led_tricolor[i][1], IOCON_PIO_DIG_FUNC0_EN);
    GPIO_PinInit(GPIO, _led_tricolor[i][0], _led_tricolor[i][1], &(gpio_pin_config_t){kGPIO_DigitalOutput, 1-LED_TRICOLO_ON});
  }
#endif

#if NEOPIXEL_NUMBER
  IOCON_PinMuxSet(IOCON, NEOPIXEL_PORT, NEOPIXEL_PIN, NEOPIXEL_IOMUX);

  sctpix_init(NEOPIXEL_TYPE);
  sctpix_addCh(NEOPIXEL_CH, _pixelData, NEOPIXEL_NUMBER);
  sctpix_setPixel(NEOPIXEL_CH, 0, 0x101000);
  sctpix_setPixel(NEOPIXEL_CH, 1, 0x101000);
  sctpix_show();
#endif

#if defined(UART_DEV) && CFG_TUSB_DEBUG
  IOCON_PinMuxSet(IOCON, UART_RX_IOMUX);
  IOCON_PinMuxSet(IOCON, UART_TX_IOMUX);

  // Enable UART when debug log is on
  CLOCK_AttachClk(kFRO12M_to_FLEXCOMM0);
  usart_config_t uart_config;
  USART_GetDefaultConfig(&uart_config);
  uart_config.baudRate_Bps = BOARD_UART_BAUDRATE;
  uart_config.enableTx     = true;
  uart_config.enableRx     = true;
  USART_Init(UART_DEV, &uart_config, 12000000);
#endif

  // Flash needs to be initialized to check for a valid image, and its PFR driver before FFR_GetUUID (UM11126 9.3.3.1)
  if (FLASH_Init(&_flash_config) != kStatus_Success || FFR_Init(&_flash_config) != kStatus_Success) {
    TU_LOG1("\r\n\r\n\t---- FLASH ERROR! ----\r\n");
  }
}

#if !defined(BUILD_NO_TINYUSB) && BOARD_TUD_RHPORT == 1
// CLOCK_EnableUsbhs0PhyPllClock() of the pinned SDK plus the > 15 us PLL regulator settling time
// of UM11126 45.3 "Initial configuration", which that SDK version lacks
static void usb1_phy_pll_init(void)
{
  POWER_DisablePD(kPDRUNCFG_PD_XTAL32M);
  POWER_DisablePD(kPDRUNCFG_PD_LDOXO32M);
  POWER_DisablePD(kPDRUNCFG_PD_FRO32K);
  POWER_DisablePD(kPDRUNCFG_PD_XTAL32K);
  POWER_DisablePD(kPDRUNCFG_PD_USB1_PHY);
  POWER_DisablePD(kPDRUNCFG_PD_LDOUSBHS);

  // wait to make sure PHY power is fully up
  for (volatile uint32_t i = 100000U; i > 0; i--) {}

  SYSCON->AHBCLKCTRLSET[2] = SYSCON_AHBCLKCTRL2_ANALOG_CTRL(1);
  SYSCON->AHBCLKCTRLSET[2] = SYSCON_AHBCLKCTRL2_USB1_PHY(1);

  USBPHY->CTRL_CLR = USBPHY_CTRL_SFTRST_MASK;

  // PLL_DIV_SEL 6: 480 MHz from the 16 MHz XTAL32M
  _Static_assert(BOARD_XTAL0_CLK_HZ == 16000000U, "PLL_DIV_SEL assumes a 16 MHz crystal");
  USBPHY->PLL_SIC     = (USBPHY->PLL_SIC & ~USBPHY_PLL_SIC_PLL_DIV_SEL(0x7)) | USBPHY_PLL_SIC_PLL_DIV_SEL(6U);
  USBPHY->PLL_SIC_SET = USBPHY_PLL_SIC_SET_PLL_REG_ENABLE_MASK;
  USBPHY->PLL_SIC_CLR = (1UL << 16U); // PLL_BYPASS

  // > 15 us at up to 150 MHz, each iteration takes more than one cycle
  for (volatile uint32_t i = 15U * 150U; i > 0; i--) {}

  USBPHY->PLL_SIC_SET = USBPHY_PLL_SIC_SET_PLL_POWER_MASK;
  USBPHY->PLL_SIC_SET = USBPHY_PLL_SIC_SET_PLL_EN_USB_CLKS_MASK;

  USBPHY->CTRL_CLR = USBPHY_CTRL_CLR_CLKGATE_MASK;
  USBPHY->PWD_SET  = 0x0;
}
#endif

void board_dfu_init(void)
{
#ifndef BUILD_NO_TINYUSB
  #if BOARD_TUD_RHPORT == 0
  // USB VBUS
  /* PORT0 PIN22 (coords: 78) is configured as USB0_VBUS */
  IOCON_PinMuxSet(IOCON, 0U, 22U, IOCON_VBUS_CONFIG);

  POWER_DisablePD(kPDRUNCFG_PD_USB0_PHY); /*Turn on USB0 Phy */

  /* reset the IP to make sure it's in reset state. */
  RESET_PeripheralReset(kUSB0D_RST_SHIFT_RSTn);
  RESET_PeripheralReset(kUSB0HSL_RST_SHIFT_RSTn);
  RESET_PeripheralReset(kUSB0HMR_RST_SHIFT_RSTn);

  // Enable USB Clock Adjustments to trim the FRO for the full speed controller
  ANACTRL->FRO192M_CTRL |= ANACTRL_FRO192M_CTRL_USBCLKADJ_MASK;
  CLOCK_SetClkDiv(kCLOCK_DivUsb0Clk, 1, false);
  CLOCK_AttachClk(kFRO_HF_to_USB0_CLK);
  /* enable usb0 host clock */
  CLOCK_EnableClock(kCLOCK_Usbhsl0);
  /*According to reference manual, device mode setting has to be set by access usb host register */
  USBFSH->PORTMODE |= USBFSH_PORTMODE_DEV_ENABLE_MASK;
  /* disable usb0 host clock */
  CLOCK_DisableClock(kCLOCK_Usbhsl0);
  CLOCK_EnableUsbfs0DeviceClock(kCLOCK_UsbfsSrcFro, CLOCK_GetFreq(kCLOCK_FroHf)); /* enable USB Device clock */
  #elif BOARD_TUD_RHPORT == 1
  // USB1_VBUS is a dedicated pin, no IOCON setup
  POWER_DisablePD(kPDRUNCFG_PD_USB1_PHY); /*< Turn on USB1 Phy */

  /* reset the IP to make sure it's in reset state. */
  RESET_PeripheralReset(kUSB1H_RST_SHIFT_RSTn);
  RESET_PeripheralReset(kUSB1D_RST_SHIFT_RSTn);
  RESET_PeripheralReset(kUSB1_RST_SHIFT_RSTn);
  RESET_PeripheralReset(kUSB1RAM_RST_SHIFT_RSTn);

  CLOCK_EnableClock(kCLOCK_Usbh1);
  /* Put PHY powerdown under software control */
  USBHSH->PORTMODE = USBHSH_PORTMODE_SW_PDCOM_MASK;
  /* According to reference manual, device mode setting has to be set by access usb host register */
  USBHSH->PORTMODE |= USBHSH_PORTMODE_DEV_ENABLE_MASK;
  /* disable usb1 host clock */
  CLOCK_DisableClock(kCLOCK_Usbh1);

  CLOCK_EnableUsbhs0DeviceClock(kCLOCK_UsbSrcUnused, 0U);
  usb1_phy_pll_init();

  // Enable all power for normal operation
  USBPHY->PWD = 0;
  USBPHY->CTRL_SET = USBPHY_CTRL_SET_ENAUTOCLR_CLKGATE_MASK;
  USBPHY->CTRL_SET = USBPHY_CTRL_SET_ENAUTOCLR_PHY_PWD_MASK;

  // PHY Tx calibration
  USBPHY->TX = ((USBPHY->TX & (~(USBPHY_TX_D_CAL_MASK | USBPHY_TX_TXCAL45DM_MASK | USBPHY_TX_TXCAL45DP_MASK))) |
                (USBPHY_TX_D_CAL(0x05U) | USBPHY_TX_TXCAL45DP(0x0AU) | USBPHY_TX_TXCAL45DM(0x0AU)));

  // USB SRAM defaults to Device memory, which faults on unaligned access: map it as Normal non-cacheable
  ARM_MPU_SetMemAttr(0, 0x44);
  ARM_MPU_SetRegion(0, ARM_MPU_RBAR(FSL_FEATURE_USBHSD_USB_RAM_BASE_ADDRESS, ARM_MPU_SH_NON, 0, 1, 1),
                    ARM_MPU_RLAR(FSL_FEATURE_USBHSD_USB_RAM_BASE_ADDRESS + FSL_FEATURE_USBHSD_USB_RAM - 1, 0));
  ARM_MPU_Enable(MPU_CTRL_PRIVDEFENA_Msk | MPU_CTRL_HFNMIENA_Msk);
  #endif
#endif

  TU_LOG2("FRO192M_CTRL:  0x%08lX\r\n", ANACTRL->FRO192M_CTRL);
}

void board_reset(void)
{
  NVIC_SystemReset();
}

void board_dfu_complete(void)
{
  NVIC_SystemReset();
}

void board_app_jump(void)
{
  uint32_t *vectorTable = (uint32_t*)BOARD_FLASH_APP_START;
  uint32_t sp = vectorTable[0];
  uint32_t pc = vectorTable[1];

  typedef void (*app_entry_t)(void);

  uint32_t s_stackPointer = 0;
  uint32_t s_applicationEntry = 0;
  app_entry_t s_application = 0;

  s_stackPointer = sp;
  s_applicationEntry = pc;
  s_application = (app_entry_t)s_applicationEntry;

  // Disable UART interrupt
  //    USART_DisableInterrupts(USART0, kUSART_RxLevelInterruptEnable | kUSART_RxErrorInterruptEnable);
  // Disable Interrupts
  NVIC->ICER[0] = 0xFFFFFFFF;
  NVIC->ICER[1] = 0xFFFFFFFF;
  // Change MSP and PSP
  __set_MSP(s_stackPointer);
  __set_PSP(s_stackPointer);

  SCB->VTOR = BOARD_FLASH_APP_START;

  // Jump to application
  s_application();

  // Should never reach here.
  __NOP();
}

//--------------------------------------------------------------------+
// LED / RGB
//--------------------------------------------------------------------+

void board_led_write(uint32_t value)
{
  // TODO PWM for fading
  GPIO_PinWrite(GPIO, LED_PORT, LED_PIN, (uint8_t)value);
}

// Write color to rgb strip
void board_rgb_write(uint8_t const rgb[])
{
#if NEOPIXEL_NUMBER
  uint32_t color = 0;    // Neopixel is GRB
  if (rgb[0]) { color += (NEOPIXEL_BRIGHTNESS <<16); }
  if (rgb[1]) { color += (NEOPIXEL_BRIGHTNESS <<8); }
  if (rgb[2]) { color += (NEOPIXEL_BRIGHTNESS); }

  sctpix_setPixel(NEOPIXEL_CH, 0, color);
  sctpix_setPixel(NEOPIXEL_CH, 1, color);
  sctpix_show();
#endif

#ifdef LED_TRICOLOR_GPIO
  for(uint8_t i=0; i<3; i++)
  {
    GPIO_PinWrite(GPIO, _led_tricolor[i][0], _led_tricolor[i][1], rgb[i] ? LED_TRICOLO_ON : (1-LED_TRICOLO_ON));
  }
#endif
}

//--------------------------------------------------------------------+
// Timer
//--------------------------------------------------------------------+

void board_timer_start(uint32_t ms)
{
  SysTick_Config( (SystemCoreClock/1000) * ms );
}

void board_timer_stop(void)
{
  SysTick->CTRL &= ~SysTick_CTRL_ENABLE_Msk;
}

void SysTick_Handler (void)
{
  board_timer_handler();
}

int board_uart_write(void const * buf, int len)
{
  USART_WriteBlocking(UART_DEV, (uint8_t *)buf, len);
  return len;
}


#ifdef TINYUF2_SELF_UPDATE

void board_self_update(const uint8_t * bootloader_bin, uint32_t bootloader_len)
{
  (void) bootloader_bin;
  (void) bootloader_len;
}

#endif

#ifndef BUILD_NO_TINYUSB

// Forward USB interrupt events to TinyUSB IRQ Handler
void USB0_IRQHandler(void)
{
  tud_int_handler(0);
}

void USB1_IRQHandler(void)
{
  tud_int_handler(1);
}

#endif
