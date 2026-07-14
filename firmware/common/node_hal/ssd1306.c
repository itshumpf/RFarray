/* Minimal SSD1306 128x64 I2C driver (new i2c_master API, IDF >= 5.2). */
#include <string.h>
#include <ctype.h>
#include <stdbool.h>
#include "ssd1306.h"
#include "driver/i2c_master.h"
#include "esp_log.h"

#define SSD1306_ADDR      0x3C
#define I2C_FREQ_HZ       400000

static const char *TAG = "ssd1306";
static i2c_master_dev_handle_t s_dev;
static uint8_t s_fb[OLED_W * OLED_H / 8];   /* 1024-byte framebuffer */

/* Classic 5x7 font, ASCII 0x20..0x5A (space .. 'Z'), column-major LSB-top. */
static const uint8_t FONT[][5] = {
    {0x00,0x00,0x00,0x00,0x00}, /*   */ {0x00,0x00,0x5F,0x00,0x00}, /* ! */
    {0x00,0x07,0x00,0x07,0x00}, /* " */ {0x14,0x7F,0x14,0x7F,0x14}, /* # */
    {0x24,0x2A,0x7F,0x2A,0x12}, /* $ */ {0x23,0x13,0x08,0x64,0x62}, /* % */
    {0x36,0x49,0x55,0x22,0x50}, /* & */ {0x00,0x05,0x03,0x00,0x00}, /* ' */
    {0x00,0x1C,0x22,0x41,0x00}, /* ( */ {0x00,0x41,0x22,0x1C,0x00}, /* ) */
    {0x14,0x08,0x3E,0x08,0x14}, /* * */ {0x08,0x08,0x3E,0x08,0x08}, /* + */
    {0x00,0x50,0x30,0x00,0x00}, /* , */ {0x08,0x08,0x08,0x08,0x08}, /* - */
    {0x00,0x60,0x60,0x00,0x00}, /* . */ {0x20,0x10,0x08,0x04,0x02}, /* / */
    {0x3E,0x51,0x49,0x45,0x3E}, /* 0 */ {0x00,0x42,0x7F,0x40,0x00}, /* 1 */
    {0x42,0x61,0x51,0x49,0x46}, /* 2 */ {0x21,0x41,0x45,0x4B,0x31}, /* 3 */
    {0x18,0x14,0x12,0x7F,0x10}, /* 4 */ {0x27,0x45,0x45,0x45,0x39}, /* 5 */
    {0x3C,0x4A,0x49,0x49,0x30}, /* 6 */ {0x01,0x71,0x09,0x05,0x03}, /* 7 */
    {0x36,0x49,0x49,0x49,0x36}, /* 8 */ {0x06,0x49,0x49,0x29,0x1E}, /* 9 */
    {0x00,0x36,0x36,0x00,0x00}, /* : */ {0x00,0x56,0x36,0x00,0x00}, /* ; */
    {0x08,0x14,0x22,0x41,0x00}, /* < */ {0x14,0x14,0x14,0x14,0x14}, /* = */
    {0x00,0x41,0x22,0x14,0x08}, /* > */ {0x02,0x01,0x51,0x09,0x06}, /* ? */
    {0x32,0x49,0x79,0x41,0x3E}, /* @ */ {0x7E,0x11,0x11,0x11,0x7E}, /* A */
    {0x7F,0x49,0x49,0x49,0x36}, /* B */ {0x3E,0x41,0x41,0x41,0x22}, /* C */
    {0x7F,0x41,0x41,0x22,0x1C}, /* D */ {0x7F,0x49,0x49,0x49,0x41}, /* E */
    {0x7F,0x09,0x09,0x09,0x01}, /* F */ {0x3E,0x41,0x49,0x49,0x7A}, /* G */
    {0x7F,0x08,0x08,0x08,0x7F}, /* H */ {0x00,0x41,0x7F,0x41,0x00}, /* I */
    {0x20,0x40,0x41,0x3F,0x01}, /* J */ {0x7F,0x08,0x14,0x22,0x41}, /* K */
    {0x7F,0x40,0x40,0x40,0x40}, /* L */ {0x7F,0x02,0x0C,0x02,0x7F}, /* M */
    {0x7F,0x04,0x08,0x10,0x7F}, /* N */ {0x3E,0x41,0x41,0x41,0x3E}, /* O */
    {0x7F,0x09,0x09,0x09,0x06}, /* P */ {0x3E,0x41,0x51,0x21,0x5E}, /* Q */
    {0x7F,0x09,0x19,0x29,0x46}, /* R */ {0x46,0x49,0x49,0x49,0x31}, /* S */
    {0x01,0x01,0x7F,0x01,0x01}, /* T */ {0x3F,0x40,0x40,0x40,0x3F}, /* U */
    {0x1F,0x20,0x40,0x20,0x1F}, /* V */ {0x3F,0x40,0x38,0x40,0x3F}, /* W */
    {0x63,0x14,0x08,0x14,0x63}, /* X */ {0x07,0x08,0x70,0x08,0x07}, /* Y */
    {0x61,0x51,0x49,0x45,0x43}, /* Z */
};

static esp_err_t cmd(uint8_t c)
{
    uint8_t b[2] = {0x00, c};
    return i2c_master_transmit(s_dev, b, 2, 100);
}

esp_err_t oled_init(int sda_gpio, int scl_gpio, bool rotate_180)
{
    i2c_master_bus_config_t bus_cfg = {
        .i2c_port = -1,
        .sda_io_num = sda_gpio,
        .scl_io_num = scl_gpio,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    i2c_master_bus_handle_t bus;
    esp_err_t err = i2c_new_master_bus(&bus_cfg, &bus);
    if (err != ESP_OK) return err;

    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = SSD1306_ADDR,
        .scl_speed_hz = I2C_FREQ_HZ,
    };
    err = i2c_master_bus_add_device(bus, &dev_cfg, &s_dev);
    if (err != ESP_OK) return err;

    const uint8_t seg_remap = rotate_180 ? 0xA0 : 0xA1;
    const uint8_t com_scan  = rotate_180 ? 0xC0 : 0xC8;

    const uint8_t init_seq[] = {
        0xAE,             /* display off */
        0xD5, 0x80,       /* clock div */
        0xA8, 0x3F,       /* multiplex 64 */
        0xD3, 0x00,       /* display offset */
        0x40,             /* start line 0 */
        0x8D, 0x14,       /* charge pump on */
        0x20, 0x00,       /* horizontal addressing */
        seg_remap,
        com_scan,
        0xDA, 0x12,       /* COM pins config for 128x64 */
        0x81, 0xCF,       /* contrast */
        0xD9, 0xF1,       /* precharge */
        0xDB, 0x40,       /* VCOM detect */
        0xA4,             /* resume from RAM */
        0xA6,             /* normal (not inverted) */
        0xAF,             /* display on */
    };
    for (size_t i = 0; i < sizeof(init_seq); i++) {
        err = cmd(init_seq[i]);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "init cmd %d failed: %s", (int)i, esp_err_to_name(err));
            return err;
        }
    }
    oled_clear();
    oled_flush();
    ESP_LOGI(TAG, "SSD1306 up (SDA=%d SCL=%d rot180=%d)", sda_gpio, scl_gpio, rotate_180);
    return ESP_OK;
}

void oled_clear(void)
{
    memset(s_fb, 0, sizeof(s_fb));
}

static void put_col(int x, int page, uint8_t bits)
{
    if (x < 0 || x >= OLED_W || page < 0 || page > 7) return;
    s_fb[page * OLED_W + x] |= bits;
}

void oled_text(int x, int page, const char *str, int scale)
{
    for (const char *p = str; *p; p++) {
        int c = toupper((unsigned char)*p);
        if (c < 0x20 || c > 0x5A) c = '?';
        const uint8_t *glyph = FONT[c - 0x20];
        for (int col = 0; col < 5; col++) {
            uint8_t bits = glyph[col];
            if (scale == 1) {
                put_col(x, page, bits);
                x++;
            } else {
                /* stretch 8 -> 16 vertical, double horizontal */
                uint16_t v = 0;
                for (int b = 0; b < 8; b++) {
                    if (bits & (1 << b)) v |= 3 << (b * 2);
                }
                for (int r = 0; r < 2; r++) {
                    put_col(x, page,     v & 0xFF);
                    put_col(x, page + 1, v >> 8);
                    x++;
                }
            }
        }
        x += scale;  /* letter spacing */
    }
}

void oled_bar(int page, int width)
{
    if (width > OLED_W) width = OLED_W;
    for (int x = 0; x < width; x++) {
        put_col(x, page, 0x3C);   /* 4-px-tall bar, vertically centered */
    }
}

void oled_vbar(int x, int h)
{
    if (h < 0) h = 0;
    if (h > OLED_H) h = OLED_H;
    int y_top = OLED_H - h;
    for (int page = 0; page < 8; page++) {
        uint8_t bits = 0;
        for (int b = 0; b < 8; b++) {
            if (page * 8 + b >= y_top) bits |= 1 << b;
        }
        if (bits) put_col(x, page, bits);
    }
}

void oled_flush(void)
{
    /* reset column/page window, then blast framebuffer */
    cmd(0x21); cmd(0x00); cmd(0x7F);   /* columns 0..127 */
    cmd(0x22); cmd(0x00); cmd(0x07);   /* pages 0..7 */

    static uint8_t buf[1 + sizeof(s_fb)];
    buf[0] = 0x40;                     /* data control byte */
    memcpy(buf + 1, s_fb, sizeof(s_fb));
    i2c_master_transmit(s_dev, buf, sizeof(buf), 200);
}
