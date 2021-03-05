#ifndef led_strip_spi_apa102_H
#define led_strip_spi_apa102_H

#include <stdio.h>
#include <string.h>
#include <math.h>
#include <stdlib.h>
#include "driver/spi_master.h"

struct led_strip_spi_apa102
{
	unsigned char *LEDs;
    short int _frameLength;
    short int _endFrameLength;
    short int _numLEDs;
    unsigned char _bytesPerLED;
    short int _counter;
    unsigned char _globalBrightness;
};

#define totalPixels 1
#define bytesPerPixel 4
#define maxValuePerColour 128
#define maxSPIFrameInBytes 8000
#define maxSPIFrequency 10000000

int setupSPI(int pin_data, int pin_clock);
void initAPA(unsigned char globalBrightness);
void setAPA(uint8_t r, uint8_t g, uint8_t b);

#endif
