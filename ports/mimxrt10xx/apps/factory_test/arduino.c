#include "arduino.h"

pinmap pinmapping[] = {
  {.num=0 , .port=GPIO1, .pin=9 , .mux={IOMUXC_GPIO_09_GPIOMUX_IO09}}  ,
  {.num=1 , .port=GPIO1, .pin=10, .mux={IOMUXC_GPIO_10_GPIOMUX_IO10}}  ,
  {.num=2 , .port=GPIO1, .pin=13, .mux={IOMUXC_GPIO_13_GPIOMUX_IO13}}  ,
  {.num=3 , .port=GPIO1, .pin=12, .mux={IOMUXC_GPIO_12_GPIOMUX_IO12}}  ,

  {.num=4 , .port=GPIO2, .pin=0 , .mux={IOMUXC_GPIO_SD_00_GPIO2_IO00}} ,
  {.num=5 , .port=GPIO2, .pin=1 , .mux={IOMUXC_GPIO_SD_01_GPIO2_IO01}} ,
  {.num=6 , .port=GPIO2, .pin=2 , .mux={IOMUXC_GPIO_SD_02_GPIO2_IO02}} ,
  {.num=7 , .port=GPIO1, .pin=11, .mux={IOMUXC_GPIO_11_GPIOMUX_IO11}}  ,

  {.num=8 , .port=GPIO1, .pin=8 , .mux={IOMUXC_GPIO_08_GPIOMUX_IO08}}  ,
  {.num=9 , .port=GPIO1, .pin=7 , .mux={IOMUXC_GPIO_07_GPIOMUX_IO07}}  ,
  {.num=10, .port=GPIO1, .pin=6 , .mux={IOMUXC_GPIO_06_GPIOMUX_IO06}}  ,
  {.num=11, .port=GPIO1, .pin=5 , .mux={IOMUXC_GPIO_05_GPIOMUX_IO05}}  ,
  {.num=12, .port=GPIO1, .pin=4 , .mux={IOMUXC_GPIO_04_GPIOMUX_IO04}}  ,
  {.num=13, .port=GPIO1, .pin=3 , .mux={IOMUXC_GPIO_03_GPIOMUX_IO03}}  ,

  {.num=14, .port=GPIO1, .pin=16, .mux={IOMUXC_GPIO_AD_02_GPIOMUX_IO16}, .adc=ADC1, .adc_channel=2 }, // AD0
  {.num=15, .port=GPIO1, .pin=15, .mux={IOMUXC_GPIO_AD_01_GPIOMUX_IO15}, .adc=ADC1, .adc_channel=1 }, // AD1
  {.num=16, .port=GPIO1, .pin=14, .mux={IOMUXC_GPIO_AD_00_GPIOMUX_IO14}, .adc=ADC1, .adc_channel=0 }, // AD2
  {.num=17, .port=GPIO1, .pin=19, .mux={IOMUXC_GPIO_AD_05_GPIOMUX_IO19}, .adc=ADC1, .adc_channel=5 }, // AD3
  {.num=18, .port=GPIO1, .pin=24, .mux={IOMUXC_GPIO_AD_10_GPIOMUX_IO24}, .adc=ADC1, .adc_channel=10 }, // AD4
  {.num=19, .port=GPIO1, .pin=22, .mux={IOMUXC_GPIO_AD_08_GPIOMUX_IO22}, .adc=ADC1, .adc_channel=8 }, // AD5

  {.num=PIN_SDA , .port=GPIO1, .pin=1 , .mux={IOMUXC_GPIO_01_GPIOMUX_IO01}}  ,
  {.num=PIN_SCL , .port=GPIO1, .pin=2 , .mux={IOMUXC_GPIO_02_GPIOMUX_IO02}}  ,

  {.num=PIN_MISO, .port=GPIO1, .pin=17, .mux={IOMUXC_GPIO_AD_03_GPIOMUX_IO17}, .adc=ADC1}, // AD0
  {.num=PIN_MOSI, .port=GPIO1, .pin=18, .mux={IOMUXC_GPIO_AD_04_GPIOMUX_IO18}, .adc=ADC1}, // AD0
  {.num=PIN_SCK , .port=GPIO1, .pin=20, .mux={IOMUXC_GPIO_AD_06_GPIOMUX_IO20}, .adc=ADC1}, // AD0
};

static volatile uint32_t _millis = 0;

void board_timer_handler(void) {
  _millis++;
}

uint32_t millis(void) {
  return _millis;
}

void delay(uint32_t ms) {
  uint32_t timestamp = millis();
  while ((timestamp+ms) > millis()) {
  //  Serial_printf("delay %d\n\r",  millis());
    tud_task();
    tud_cdc_write_flush();
  }
}


static pinmap *getMapping(uint32_t pinnum) {
  pinmap *pindeets = NULL;

  for (uint32_t i=0; i<sizeof(pinmapping) / sizeof(pinmap); i++) {
    pindeets = &pinmapping[i];
    //Serial_printf("pin %d -> port %x, pin %d\n\r",  pindeets->num, pindeets->port, pindeets->pin);
    if (pinnum == pindeets->num) {
      //Serial_printf("found!\n\r");
      return pindeets;
    }
  }
  return NULL;
}


void digitalWrite(uint32_t pinnum, bool value) {
  pinmap *pindeets = getMapping(pinnum);
  if (! pindeets) return;

  GPIO_PinWrite(pindeets->port, pindeets->pin, value);
}

bool digitalRead(uint32_t pinnum) {
  pinmap *pindeets = getMapping(pinnum);
  if (! pindeets) return 0;


  return GPIO_PinRead(pindeets->port, pindeets->pin);
}

void pinMode(uint32_t pinnum, uint8_t state) {
  pinmap *pindeets = getMapping(pinnum);
  if (! pindeets) return;

  IOMUXC_SetPinMux(pindeets->mux.muxReg, pindeets->mux.muxMode,
                   pindeets->mux.inputReg, pindeets->mux.idaisy,
                   pindeets->mux.configReg, 0U);
  IOMUXC_SetPinConfig(pindeets->mux.muxReg, pindeets->mux.muxMode,
                      pindeets->mux.inputReg, pindeets->mux.idaisy,
                      pindeets->mux.configReg, 0x10B0U);

  if (state == OUTPUT) {
    gpio_pin_config_t pin_config = { kGPIO_DigitalOutput, 0, kGPIO_NoIntmode };
    GPIO_PinInit(pindeets->port, pindeets->pin, &pin_config);
  } else {
    gpio_pin_config_t pin_config = { kGPIO_DigitalInput, 0, kGPIO_NoIntmode };
    GPIO_PinInit(pindeets->port, pindeets->pin, &pin_config);

    if (state == INPUT_PULLUP) {
      IOMUXC_SetPinConfig(pindeets->mux.muxReg, pindeets->mux.muxMode,
                          pindeets->mux.inputReg, pindeets->mux.idaisy,
                          pindeets->mux.configReg, 0xB0B0U);
    }
  }
}

void setColor(uint32_t color) {
  uint8_t rgb[3] = {(color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF};
  board_rgb_write(rgb);
}

uint32_t makeColor(uint8_t r, uint8_t g, uint8_t b) {
  uint32_t c = 0;
  c |= r;
  c <<= 8;
  c |= g;
  c <<= 8;
  c |= b;
  return c;
}

uint32_t neoWheel(uint8_t WheelPos) {
  WheelPos = 255 - WheelPos;
  if (WheelPos < 85) {
    return makeColor(255 - WheelPos * 3, 0, WheelPos * 3);
  }
  if (WheelPos < 170) {
    WheelPos -= 85;
    return makeColor(0, WheelPos * 3, 255 - WheelPos * 3);
  }
  WheelPos -= 170;
  return makeColor(WheelPos * 3, 255 - WheelPos * 3, 0);
}


int analogRead(uint32_t pinnum)
{
  enum { ADC_CHANNEL_GROUP = 0 };
  static bool adc_hw_inited = false;

  pinmap *pindeets = getMapping(pinnum);
  if (! pindeets) return -1;
  if (! pindeets->adc) return -1;

  if (!pindeets->adc_inited)
  {
    if (!adc_hw_inited)
    {
      adc_config_t config = {0};

      ADC_GetDefaultConfig(&config);
      config.enableLongSample = true;
      config.samplePeriodMode = kADC_SamplePeriod8or24Clocks;

      ADC_Init(pindeets->adc, &config);
      ADC_SetHardwareAverageConfig(pindeets->adc, kADC_HardwareAverageCount32);
      ADC_DoAutoCalibration(pindeets->adc);

      adc_hw_inited = true;
    }

    pindeets->adc_inited = true;
  }

  /* When in software trigger mode, each conversion would be launched once calling the "ADC_ChannelConfigure()"
     function, which works like writing a conversion command and executing it. For another channel's conversion,
     just to change the "channelNumber" field in channel's configuration structure, and call the
     "ADC_ChannelConfigure() again.
   */
  adc_channel_config_t config = {
    .channelNumber = pindeets->adc_channel
  };
  ADC_SetChannelConfig(pindeets->adc, ADC_CHANNEL_GROUP, &config);

  while (0U == ADC_GetChannelStatusFlags(pindeets->adc, ADC_CHANNEL_GROUP))
  {
  }

  // value is 12-bit resolution
  uint16_t value = ADC_GetChannelConversionValue(pindeets->adc, ADC_CHANNEL_GROUP);

  return value;
}
