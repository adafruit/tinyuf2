/*
 * The MIT License (MIT)
 *
 * Copyright (c) Henry Gabryjelski
 * Copyright (c) Ha Thach for Adafruit Industries
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

#ifndef COMPILE_DATE_H
#define COMPILE_DATE_H

#ifndef __PERSISTENT_COMPILATION_DATE__
  #define __PERSISTENT_COMPILATION_DATE__ __DATE__
#endif

#ifndef __PERSISTENT_COMPILATION_TIME__
  #define __PERSISTENT_COMPILATION_TIME__ __TIME__
#endif



#define __YEAR_INT__ ((( \
  (__PERSISTENT_COMPILATION_DATE__ [ 7u] - '0')  * 10u + \
  (__PERSISTENT_COMPILATION_DATE__ [ 8u] - '0')) * 10u + \
  (__PERSISTENT_COMPILATION_DATE__ [ 9u] - '0')) * 10u + \
  (__PERSISTENT_COMPILATION_DATE__ [10u] - '0'))

#define __MONTH_INT__ ( \
    (__PERSISTENT_COMPILATION_DATE__ [2u] == 'n' && __PERSISTENT_COMPILATION_DATE__ [1u] == 'a') ?  1u  /*Jan*/ \
  : (__PERSISTENT_COMPILATION_DATE__ [2u] == 'b'                                               ) ?  2u  /*Feb*/ \
  : (__PERSISTENT_COMPILATION_DATE__ [2u] == 'r' && __PERSISTENT_COMPILATION_DATE__ [1u] == 'a') ?  3u  /*Mar*/ \
  : (__PERSISTENT_COMPILATION_DATE__ [2u] == 'r'                                               ) ?  4u  /*Apr*/ \
  : (__PERSISTENT_COMPILATION_DATE__ [2u] == 'y'                                               ) ?  5u  /*May*/ \
  : (__PERSISTENT_COMPILATION_DATE__ [2u] == 'n'                                               ) ?  6u  /*Jun*/ \
  : (__PERSISTENT_COMPILATION_DATE__ [2u] == 'l'                                               ) ?  7u  /*Jul*/ \
  : (__PERSISTENT_COMPILATION_DATE__ [2u] == 'g'                                               ) ?  8u  /*Aug*/ \
  : (__PERSISTENT_COMPILATION_DATE__ [2u] == 'p'                                               ) ?  9u  /*Sep*/ \
  : (__PERSISTENT_COMPILATION_DATE__ [2u] == 't'                                               ) ? 10u  /*Oct*/ \
  : (__PERSISTENT_COMPILATION_DATE__ [2u] == 'v'                                               ) ? 11u  /*Nov*/ \
  :                                                                                                12u  /*Dec*/ )

#define __DAY_INT__ ( \
   (__PERSISTENT_COMPILATION_DATE__ [4u] == ' ' ? 0 : __PERSISTENT_COMPILATION_DATE__ [4u] - '0') * 10u \
 + (__PERSISTENT_COMPILATION_DATE__ [5u] - '0')                                   )

// __TIME__ expands to an eight-character string constant
// "23:59:01", or (if cannot determine time) "??:??:??" 
#define __HOUR_INT__ ( \
   (__PERSISTENT_COMPILATION_TIME__ [0u] == '?' ? 0 : __PERSISTENT_COMPILATION_TIME__ [0u] - '0') * 10u \
 + (__PERSISTENT_COMPILATION_TIME__ [1u] == '?' ? 0 : __PERSISTENT_COMPILATION_TIME__ [1u] - '0')       )

#define __MINUTE_INT__ ( \
   (__PERSISTENT_COMPILATION_TIME__ [3u] == '?' ? 0 : __PERSISTENT_COMPILATION_TIME__ [3u] - '0') * 10u \
 + (__PERSISTENT_COMPILATION_TIME__ [4u] == '?' ? 0 : __PERSISTENT_COMPILATION_TIME__ [4u] - '0')       )

#define __SECONDS_INT__ ( \
   (__PERSISTENT_COMPILATION_TIME__ [6u] == '?' ? 0 : __PERSISTENT_COMPILATION_TIME__ [6u] - '0') * 10u \
 + (__PERSISTENT_COMPILATION_TIME__ [7u] == '?' ? 0 : __PERSISTENT_COMPILATION_TIME__ [7u] - '0')       )


#define __DOSDATE__ ( \
	((__YEAR_INT__  - 1980u) << 9u) | \
	( __MONTH_INT__          << 5u) | \
	( __DAY_INT__            << 0u) )

#define __DOSTIME__ ( \
	( __HOUR_INT__    << 11u) | \
	( __MINUTE_INT__  <<  5u) | \
	( __SECONDS_INT__ <<  0u) )

#endif // COMPILE_DATE_H

