#include "board_api.h"
#include "led_strip.h"

extern led_strip_t *strip;

uint8_t upload_symbol[10] = {19, 20, 26, 27, 28, 29, 35, 36, 43, 44};
uint8_t upload_animation_line[4][3] = {{18, 19, 20},
                                       {21, 29, 37},
                                       {45, 44, 43},
                                       {42, 34, 26}};



void show_upload_symbol(uint8_t r, uint8_t g, uint8_t b)
{
  for(uint32_t i=0; i<sizeof(upload_symbol); i++)
  {
    strip->set_pixel(strip, upload_symbol[i], r, g, b);
  }
  strip->refresh(strip, 100);
}

uint32_t current_state;
void board_rgb_state(uint32_t state)
{
    current_state = state;
    switch (state)
    {
    case STATE_USB_UNPLUGGED:
        show_upload_symbol(255, 0, 0);
        break;

    case STATE_USB_PLUGGED:
        show_upload_symbol(0, 255, 0);
        break;

    case STATE_WRITING_STARTED:
        board_timer_start(25);
        break;

    case STATE_WRITING_FINISHED:
        board_timer_stop();
        break;

    default:
        break; // nothing to do
    }
}

void board_timer_handler()
{
}