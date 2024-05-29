# KUIIC RGB Multiplexing Driver

The KUIIC board uses two timer capable pins to drive an RGB LED.  This was done to provide a full color indicator without consuming the 6ch timer resource in the K32L2B.  This driver enables full color on the LED with a two channel timer/PWM.

## Theory of operation

The three LEDS are connected in the following order:

```
         red  B/R#      blue G/B#      green
3V3 - 2k ->|- PTA1 - 1k ->|- PTA2 - 2k ->|- GND
```

The state of the LEDs is described in the following truth table:

 B/R#  | G/B#  |  R  |  G  |  B  | Color
-------|-------|-----|-----|-----|-------
   Z   |   Z   | off | off | off | black
   0   |   0   | ON  | off | off | red
   0   |   1   | ON  | ON  | off | yellow
   1   |   0   | off | off | ON  | blue
   1   |   1   | off | ON  | off | green

As seen in the table, with simple GPIO control including tri-state, 5 combinations are possible including black, R, G, B, and yellow as a bonus color option.  Implementing these 5 options is left as an exercise for the reader.  This driver enables generating 24bit RGB color using two timer channels.

## Timer operation

At the beginning of a new period, the timer will drive both channels high generating green.  After the green count expires, it will drive the second channel (CH 1, G/B#) low changing the color to blue.  After the green + blue count expires, the first channel (CH 0, B/R#) is driven low to output red.  The timer is disabled after green + blue + red counts expire.  The process repeats at the next SysTick interrupt when the timer is enabled.

To implement this with the timer:
 * TPM Channel 1 (G/B#) Value is loaded with the green RGB value
 * TPM Channel 0 (B/R#) Value is loaded with the green + blue values
 * TPM Modulo is loaded with the green + blue + red values
 * The timer is configured to trigger a DMA transfer when the modulo count exprires that will disable (tri-state) the outputs
 * The timer is enabled at every SysTick interrupt

## Clocking

This library utilizes the 48MHz clock that is required for USB operation.  It sets the prescaler to divide by 1 for the highest resolution.  KUIIC_RGB_BRIGHT_SHIFT is provided to allow for maximum brightness addjustments.  The three color counts need to be completed within the 1ms SysTick interval which is 48,000 clocks when running at 48MHz, therefore the maximum count needs to be less than 16,000 for each color and KUIIC_RGB_BRIGHT_SHIFT should not be set above 5 (255 * 2^5 = 8160).
