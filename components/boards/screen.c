#include "boards.h"

#if USE_SCREEN

#include <string.h>
#include "lcd.h"

//#define DISPLAY_WIDTH 160
//#define DISPLAY_HEIGHT 128

// Overlap 4x chars by this much.
#define CHAR4_KERNING 2
// Width of a single 4x char, adjusted by kerning
#define CHAR4_KERNED_WIDTH  (6 * 4 - CHAR4_KERNING)

#define ST7735_NOP 0x00
#define ST7735_SWRESET 0x01
#define ST7735_RDDID 0x04
#define ST7735_RDDST 0x09

#define ST7735_SLPIN 0x10
#define ST7735_SLPOUT 0x11
#define ST7735_PTLON 0x12
#define ST7735_NORON 0x13

#define ST7735_INVOFF 0x20
#define ST7735_INVON 0x21
#define ST7735_DISPOFF 0x28
#define ST7735_DISPON 0x29
#define ST7735_CASET 0x2A
#define ST7735_RASET 0x2B
#define ST7735_RAMWR 0x2C
#define ST7735_RAMRD 0x2E

#define ST7735_PTLAR 0x30
#define ST7735_COLMOD 0x3A
#define ST7735_MADCTL 0x36

#define ST7735_FRMCTR1 0xB1
#define ST7735_FRMCTR2 0xB2
#define ST7735_FRMCTR3 0xB3
#define ST7735_INVCTR 0xB4
#define ST7735_DISSET5 0xB6

#define ST7735_PWCTR1 0xC0
#define ST7735_PWCTR2 0xC1
#define ST7735_PWCTR3 0xC2
#define ST7735_PWCTR4 0xC3
#define ST7735_PWCTR5 0xC4
#define ST7735_VMCTR1 0xC5

#define ST7735_RDID1 0xDA
#define ST7735_RDID2 0xDB
#define ST7735_RDID3 0xDC
#define ST7735_RDID4 0xDD

#define ST7735_PWCTR6 0xFC

#define ST7735_GMCTRP1 0xE0
#define ST7735_GMCTRN1 0xE1

#if 0
uint32_t lookupCfg(uint32_t key, uint32_t defl);
#define CFG(v) lookupCfg(CFG_##v, 0x42)

uint32_t lookupCfg(uint32_t key, uint32_t defl) {
    const uint32_t *ptr = UF2_BINFO->config_data;
    if (!ptr || (((uint32_t)ptr) & 3) || *ptr != CFG_MAGIC0) {
        // no config data!
    } else {
        ptr += 4;
        while (*ptr) {
            if (*ptr == key)
                return ptr[1];
            ptr += 2;
        }
    }
    if (defl == 0x42)
        while (1)
            ;
    return defl;
}

void pin_set(int pincfg, int v) {
    int pin = lookupCfg(pincfg, -1);
    if (pin < 0)
        return;
    if (v) {
        PINOP(pin, OUTSET);
    } else {
        PINOP(pin, OUTCLR);
    }
}

void setup_output_pin(int pincfg) {
    int pin = lookupCfg(pincfg, -1);
    if (pin < 0)
        return;
    PINOP(pin, DIRSET);
    PINOP(pin, OUTCLR);
}

#define PINPORT(pin) PORT->Group[(pin) / 32]
#define pinmask(pin) (1 << (pin & 0x1f))

void transfer(uint8_t *ptr, uint32_t len) {
    int mosi = CFG(PIN_DISPLAY_MOSI);
    int sck = CFG(PIN_DISPLAY_SCK);

    volatile uint32_t *mosi_set = &PINPORT(mosi).OUTSET.reg;
    volatile uint32_t *mosi_clr = &PINPORT(mosi).OUTCLR.reg;
    volatile uint32_t *sck_tgl = &PINPORT(sck).OUTTGL.reg;

    uint32_t mosi_mask = pinmask(mosi);
    uint32_t sck_mask = pinmask(sck);

    PINOP(sck, OUTCLR);

    uint8_t mask = 0, b;
    for (;;) {
        if (!mask) {
            if (!len--)
                break;
            mask = 0x80;
            b = *ptr++;
        }
        if (b & mask)
            *mosi_set = mosi_mask;
        else
            *mosi_clr = mosi_mask;
        *sck_tgl = sck_mask;
        mask >>= 1;
        *sck_tgl = sck_mask;
    }
}

#define DELAY 0x80

// clang-format off
static const uint8_t initCmds[] = {
    ST7735_SWRESET,   DELAY,  //  1: Software reset, 0 args, w/delay
      120,                    //     150 ms delay
    ST7735_SLPOUT ,   DELAY,  //  2: Out of sleep mode, 0 args, w/delay
      120,                    //     500 ms delay
    ST7735_INVOFF , 0      ,  // 13: Don't invert display, no args, no delay
    ST7735_COLMOD , 1      ,  // 15: set color mode, 1 arg, no delay:
      0x05,                  //     16-bit color
    ST7735_GMCTRP1, 16      , //  1: Magical unicorn dust, 16 args, no delay:
      0x02, 0x1c, 0x07, 0x12,
      0x37, 0x32, 0x29, 0x2d,
      0x29, 0x25, 0x2B, 0x39,
      0x00, 0x01, 0x03, 0x10,
    ST7735_NORON  ,    DELAY, //  3: Normal display on, no args, w/delay
      10,                     //     10 ms delay
    ST7735_DISPON ,    DELAY, //  4: Main screen turn on, no args w/delay
      10,
    0, 0 // END
};
// clang-format on

static uint8_t cmdBuf[20];

#define SET_DC(v) pin_set(CFG_PIN_DISPLAY_DC, v)
#define SET_CS(v) pin_set(CFG_PIN_DISPLAY_CS, v)

static void scr_delay(unsigned msec) {
    int k = msec * 15000;
    while (k--)
        asm("nop");
}

static void sendCmd(uint8_t *buf, int len) {
    // make sure cmd isn't on stack
    if (buf != cmdBuf)
        memcpy(cmdBuf, buf, len);
    buf = cmdBuf;

    SET_DC(0);
    SET_CS(0);

    transfer(buf, 1);

    SET_DC(1);

    len--;
    buf++;
    if (len > 0)
        transfer(buf, len);

    SET_CS(1);
}

static void sendCmdSeq(const uint8_t *buf) {
    while (*buf) {
        cmdBuf[0] = *buf++;
        int v = *buf++;
        int len = v & ~DELAY;
        // note that we have to copy to RAM
        memcpy(cmdBuf + 1, buf, len);
        sendCmd(cmdBuf, len + 1);
        buf += len;
        if (v & DELAY) {
            scr_delay(*buf++);
        }
    }
}

static uint32_t palXOR;

static void setAddrWindow(int x, int y, int w, int h) {
    uint8_t cmd0[] = {ST7735_RASET, 0, (uint8_t)x, 0, (uint8_t)(x + w - 1)};
    uint8_t cmd1[] = {ST7735_CASET, 0, (uint8_t)y, 0, (uint8_t)(y + h - 1)};
    sendCmd(cmd1, sizeof(cmd1));
    sendCmd(cmd0, sizeof(cmd0));
}

static void configure(uint8_t madctl, uint32_t frmctr1) {
    uint8_t cmd0[] = {ST7735_MADCTL, madctl};
    uint8_t cmd1[] = {ST7735_FRMCTR1, (uint8_t)(frmctr1 >> 16), (uint8_t)(frmctr1 >> 8),
                      (uint8_t)frmctr1};
    sendCmd(cmd0, sizeof(cmd0));
    sendCmd(cmd1, cmd1[3] == 0xff ? 3 : 4);
}

#define COL0(r, g, b) ((((r) >> 3) << 11) | (((g) >> 2) << 5) | ((b) >> 3))
#define COL(c) COL0((c >> 16) & 0xff, (c >> 8) & 0xff, c & 0xff)

const uint16_t palette[] = {
    COL(0x000000), // 0
    COL(0xffffff), // 1
    COL(0xff2121), // 2
    COL(0xff93c4), // 3
    COL(0xff8135), // 4
    COL(0xfff609), // 5
    COL(0x249ca3), // 6
    COL(0x78dc52), // 7
    COL(0x003fad), // 8
    COL(0x87f2ff), // 9
    COL(0x8e2ec4), // 10
    COL(0xa4839f), // 11
    COL(0x5c406c), // 12
    COL(0xe5cdc4), // 13
    COL(0x91463d), // 14
    COL(0x000000), // 15
};

uint8_t fb[168 * 128];
extern const uint8_t font8[];
extern const uint8_t fileLogo[];
extern const uint8_t pendriveLogo[];
extern const uint8_t arrowLogo[];

static void printch(int x, int y, int col, const uint8_t *fnt) {
    for (int i = 0; i < 6; ++i) {
        uint8_t *p = fb + (x + i) * DISPLAY_HEIGHT + y;
        uint8_t mask = 0x01;
        for (int j = 0; j < 8; ++j) {
            if (*fnt & mask)
                *p = col;
            p++;
            mask <<= 1;
        }
        fnt++;
    }
}

static void printch4(int x, int y, int col, const uint8_t *fnt) {
    for (int i = 0; i < 6 * 4; ++i) {
        uint8_t *p = fb + (x + i) * DISPLAY_HEIGHT + y;
        uint8_t mask = 0x01;
        for (int j = 0; j < 8; ++j) {
            for (int k = 0; k < 4; ++k) {
                if (*fnt & mask)
                    *p = col;
                p++;
            }
            mask <<= 1;
        }
        if ((i & 3) == 3)
            fnt++;
    }
}

void printicon(int x, int y, int col, const uint8_t *icon) {
    int w = *icon++;
    int h = *icon++;
    int sz = *icon++;

    uint8_t mask = 0x80;
    int runlen = 0;
    int runbit = 0;
    uint8_t lastb = 0x00;

    for (int i = 0; i < w; ++i) {
        uint8_t *p = fb + (x + i) * DISPLAY_HEIGHT + y;
        for (int j = 0; j < h; ++j) {
            int c = 0;
            if (mask != 0x80) {
                if (lastb & mask)
                    c = 1;
                mask <<= 1;
            } else if (runlen) {
                if (runbit)
                    c = 1;
                runlen--;
            } else {
                if (sz-- <= 0)
                    panic(10);
                lastb = *icon++;
                if (lastb & 0x80) {
                    runlen = lastb & 63;
                    runbit = lastb & 0x40;
                } else {
                    mask = 0x01;
                }
                --j;
                continue; // restart
            }
            if (c)
                *p = col;
            p++;
        }
    }
}

void print(int x, int y, int col, const char *text) {
    int x0 = x;
    while (*text) {
        char c = *text++;
        if (c == '\r')
            continue;
        if (c == '\n') {
            x = x0;
            y += 10;
            continue;
        }
        /*
        if (x + 8 > DISPLAY_WIDTH) {
            x = x0;
            y += 10;
        }
        */
        if (c < ' ')
            c = '?';
        if (c >= 0x7f)
            c = '?';
        c -= ' ';
        printch(x, y, col, &font8[c * 6]);
        x += 6;
    }
}

void print4(int x, int y, int col, const char *text) {
    while (*text) {
        char c = *text++;
        c -= ' ';
        printch4(x, y, col, &font8[c * 6]);
        x += CHAR4_KERNED_WIDTH;
        if (x + CHAR4_KERNED_WIDTH > DISPLAY_WIDTH) {
            // Next char won't fit.
            return;
        }
    }
}

void draw_screen() {
    if (lookupCfg(CFG_PIN_DISPLAY_SCK, 1000) == 1000)
        return;

    cmdBuf[0] = ST7735_RAMWR;
    sendCmd(cmdBuf, 1);

    SET_DC(1);
    SET_CS(0);

    uint8_t *p = fb;
    for (int i = 0; i < DISPLAY_WIDTH; ++i) {
        uint8_t cc[DISPLAY_HEIGHT * 2];
        uint32_t dst = 0;
        for (int j = 0; j < DISPLAY_HEIGHT; ++j) {
            uint16_t color = palette[*p++ & 0xf];
            cc[dst++] = color >> 8;
            cc[dst++] = color & 0xff;
        }
        transfer(cc, sizeof(cc));
    }

    SET_CS(1);
}

void drawBar(int y, int h, int c) {
    for (int x = 0; x < DISPLAY_WIDTH; ++x) {
        memset(fb + x * DISPLAY_HEIGHT + y, c, h);
    }
}

void draw_hf2() {
    print4(20, 22, 5, "<-->");
    print(40, 110, 7, "flashing...");
    draw_screen();
}

void draw_drag() {
    drawBar(0, 52, 7);
    drawBar(52, 55, 8);
    drawBar(107, 14, 4);

    // Center PRODUCT_NAME and UF2_VERSION_BASE.
    int name_x = (DISPLAY_WIDTH - (6 * 4 - CHAR4_KERNING) * (int) strlen(PRODUCT_NAME)) / 2;
    print4(name_x >= 0 ? name_x : 0, 5, 1, PRODUCT_NAME);
    int version_x = (DISPLAY_WIDTH - 6 * (int) strlen(UF2_VERSION_BASE)) / 2;
    print(version_x >= 0 ? version_x : 0, 40, 6, UF2_VERSION_BASE);
    print(23, 110, 1, "arcade.makecode.com");

#define DRAG 70
#define DRAGX 10
    printicon(DRAGX + 20, DRAG + 5, 1, fileLogo);
    printicon(DRAGX + 66, DRAG, 1, arrowLogo);
    printicon(DRAGX + 108, DRAG, 1, pendriveLogo);
    print(10, DRAG - 12, 1, "arcade.uf2");
    print(90, DRAG - 12, 1, VOLUME_LABEL);

    draw_screen();
}

#endif

void screen_init(void)
{
  spi_device_handle_t spi = {0};

  spi_bus_config_t bus_cfg = {
    .miso_io_num     = PIN_DISPLAY_MISO,
    .mosi_io_num     = PIN_DISPLAY_MOSI,
    .sclk_io_num     = PIN_DISPLAY_SCK,
    .quadwp_io_num   = -1,
    .quadhd_io_num   = -1,
    .max_transfer_sz = PARALLEL_LINES * 320 * 2 + 8
  };

  spi_device_interface_config_t devcfg = {
    .clock_speed_hz = 10 * 1000 * 1000,              /*!< Clock out at 10 MHz */
    .mode           = 0,                             /*!< SPI mode 0 */
    .spics_io_num   = PIN_DISPLAY_CS,                    /*!< CS pin */
    .queue_size     = 7,                             /*!< We want to be able to queue 7 transactions at a time */
    .pre_cb         = lcd_spi_pre_transfer_callback, /*!< Specify pre-transfer callback to handle D/C line */
  };

  /*!< Initialize the SPI bus */
  ESP_ERROR_CHECK(spi_bus_initialize(LCD_HOST, &bus_cfg, DMA_CHAN));

  /*!< Attach the LCD to the SPI bus */
  ESP_ERROR_CHECK(spi_bus_add_device(LCD_HOST, &devcfg, &spi));

  /**< Initialize the LCD */
  ESP_ERROR_CHECK(lcd_init(spi));

#if 0
    uint32_t cfg0 = CFG(DISPLAY_CFG0);
    //uint32_t cfg2 = CFG(DISPLAY_CFG2);
    uint32_t frmctr1 = CFG(DISPLAY_CFG1);
    palXOR = (cfg0 & 0x1000000) ? 0xffffff : 0x000000;
    uint32_t madctl = cfg0 & 0xff;
    uint32_t offX = (cfg0 >> 8) & 0xff;
    uint32_t offY = (cfg0 >> 16) & 0xff;
    //uint32_t freq = (cfg2 & 0xff);

    // DMESG("configure screen: FRMCTR1=%p MADCTL=%p SPI at %dMHz", frmctr1, madctl, freq);
    configure(madctl, frmctr1);
    setAddrWindow(offX, offY, CFG(DISPLAY_WIDTH), CFG(DISPLAY_HEIGHT));
#endif

    memset(fb, 0, sizeof(fb));
}

#endif
