#include "board_api.h"

#if (TINYUF2_DISPLAY == 1U)
#include "components/st7735/st7735.h"

SPI_HandleTypeDef _display_spi;
#endif // TINYUF2_DISPLAY == 1U

//--------------------------------------------------------------------+
// Board Display Callouts
//--------------------------------------------------------------------+
#if (TINYUF2_DISPLAY == 1)
void ST7735_Transmit(uint8_t * buffer, uint16_t len, uint32_t timeout)
{
  HAL_SPI_Transmit(&_display_spi, buffer, len, timeout);
}

void ST7735_Delay(uint32_t ms)
{
  HAL_Delay(ms);
}

void board_display_init(void)
{
  display_init(&_display_spi);
  ST7735_Init();
  // Clear previous screen
  ST7735_FillScreen(ST7735_BLACK);
}

// The application draws a complete frame in memory and sends it
// line-by-line to the display
void board_display_draw_line(int y, uint16_t* pixel_color, uint32_t pixel_num)
{
  for (uint32_t x = 0; x < pixel_num; x += 1) {
    ST7735_DrawPixel(y, x, pixel_color[x]);
  }
}
#endif // TINYUF2_DISPLAY == 1U

//--------------------------------------------------------------------+
// LED pattern
//--------------------------------------------------------------------+
#if defined(TINYUF2_LED)
void board_led_write(uint32_t state)
{
  HAL_GPIO_WritePin(LED_PORT, LED_PIN, state ? GPIO_PIN_SET : GPIO_PIN_RESET);
}
#endif // defined(LED_PIN)

//--------------------------------------------------------------------+
// Button
//--------------------------------------------------------------------+
#if defined(BUTTON_PIN)
uint32_t board_button_read(void)
{
  return (BUTTON_STATE_ACTIVE == HAL_GPIO_ReadPin(BUTTON_PORT, BUTTON_PIN)) ? 1: 0;
}
#endif // defined(BUTTON_PIN)

//--------------------------------------------------------------------+
// Neopixel color for status
//--------------------------------------------------------------------+
void board_rgb_write(uint8_t const rgb[])
{
  // TODO: copy neopixel code from f4 port
  (void) rgb;
}
