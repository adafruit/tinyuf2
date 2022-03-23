#include "board_api.h"
#include "led_strip.h"

extern led_strip_t *strip;

uint8_t upload_symbol[10] = {19, 20, 27, 28, 34, 35, 36, 37, 43, 44};

#define WAVE_STEP 16
uint8_t* grayscale_wave;





void show_upload_symbol(uint8_t r, uint8_t g, uint8_t b)
{
  for(uint32_t i = 0; i < sizeof(upload_symbol); i++)
  {
    strip->set_pixel(strip, upload_symbol[i], r, g, b);
  }
  strip->refresh(strip, 100);
}

void generate_wave()
{
    grayscale_wave = malloc(WAVE_STEP);
    grayscale_wave[0] = 255;

    float exp = 1.11; // 2.2 ^ (1/(WAVE_STEP / 4))

    for(uint8_t i = 1; i < WAVE_STEP; i++)
    {
        grayscale_wave[i] = grayscale_wave[i - 1] / exp;
    }
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
        generate_wave();
        board_timer_start(25);
        break;

    case STATE_WRITING_FINISHED:
        board_timer_stop();
        strip->clear(strip, 100);
        break;

    default:
        break; // nothing to do
    }
}

uint8_t led_index = 0;
void board_timer_handler()
{
    if(current_state == STATE_WRITING_STARTED)
    {
        for(uint8_t i = 0; i < sizeof(upload_symbol); i++)
        {
            uint8_t y = upload_symbol[i] / 8 - 2;
            if(y >= led_index)
                break;
            uint8_t brightness = grayscale_wave[((4-y) + led_index) % WAVE_STEP];
            strip->set_pixel(strip, upload_symbol[i], 0, brightness, brightness);
        }
    }
    led_index ++;
    strip->refresh(strip, 100);
}