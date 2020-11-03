#include "led_strip_spi_apa102.h"

//SPI Vars
spi_device_handle_t spi;
spi_transaction_t spiTransObject;
esp_err_t ret;
spi_bus_config_t buscfg;
spi_device_interface_config_t devcfg;

// APA LED struct
struct led_strip_spi_apa102 led;

void initAPA(unsigned char globalBrightness)
{  
  led._numLEDs = totalPixels;
  led._bytesPerLED = bytesPerPixel;
  led._endFrameLength = 1;//round( (numLEDs/2)/8 );
  led._frameLength = (1+led._numLEDs+led._endFrameLength)*led._bytesPerLED;
  led._globalBrightness = globalBrightness;
  led.LEDs = (unsigned char *)malloc(led._frameLength*sizeof(unsigned char)); 
  
  //Start Frame
  led.LEDs[0] = 0;
  led.LEDs[1] = 0;
  led.LEDs[2] = 0;
  led.LEDs[3] = 0;
  //Driver frame+PIXEL frames
  for(led._counter=led._bytesPerLED; led._counter<led._frameLength-(led._endFrameLength*led._bytesPerLED); led._counter+=led._bytesPerLED)
  {
    led.LEDs[led._counter] = led._globalBrightness;
    led.LEDs[led._counter+1] = 0;
    led.LEDs[led._counter+2] = 0;
    led.LEDs[led._counter+3] = 0;
  }
  //END frames
  for(led._counter=led._frameLength-(led._endFrameLength*led._bytesPerLED); led._counter<led._frameLength; led._counter+=led._bytesPerLED)
  {
    led.LEDs[led._counter] = 255;
    led.LEDs[led._counter+1] = 255;
    led.LEDs[led._counter+2] = 255;
    led.LEDs[led._counter+3] = 255;
  }


    //Set up SPI tx/rx storage Object
	memset(&spiTransObject, 0, sizeof(spiTransObject));
	spiTransObject.length = led._frameLength*8;
	spiTransObject.tx_buffer = led.LEDs;

	//Sending SPI data block to clear all pixels
	spi_device_queue_trans(spi, &spiTransObject, portMAX_DELAY);
}

void setAPA(uint8_t r, uint8_t g, uint8_t b)
{
  int pixelIndex = 0;
  led._counter = 4*(pixelIndex+1);
  led.LEDs[ led._counter + 1 ] = b;
  led.LEDs[ led._counter + 2 ] = g;
  led.LEDs[ led._counter + 3 ] = r;

  spi_device_queue_trans(spi, &spiTransObject, portMAX_DELAY);
}

int setupSPI(int pin_data, int pin_clock)
{
	//Set up the Bus Config struct
	buscfg.miso_io_num=-1;
	buscfg.mosi_io_num=pin_data;
	buscfg.sclk_io_num=pin_clock;
	buscfg.quadwp_io_num=-1;
	buscfg.quadhd_io_num=-1;
	buscfg.max_transfer_sz=maxSPIFrameInBytes;
	
	//Set up the SPI Device Configuration Struct
	devcfg.clock_speed_hz=maxSPIFrequency;
	devcfg.mode=0;                        
	devcfg.spics_io_num=-1;             
	devcfg.queue_size=1;

	//Initialize the SPI driver
	ret=spi_bus_initialize(SPI2_HOST, &buscfg, 1);
    ESP_ERROR_CHECK(ret);	
	//Add SPI port to bus
	ret=spi_bus_add_device(SPI2_HOST, &devcfg, &spi);
	ESP_ERROR_CHECK(ret);
	return ret;
}