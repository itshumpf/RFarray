/* Minimal SSD1306 128x64 I2C driver with 5x7 text rendering. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#define OLED_W 128
#define OLED_H 64

esp_err_t oled_init(int sda_gpio, int scl_gpio, bool rotate_180);
void oled_clear(void);
/* Draw ASCII text (uppercased) at column x (pixels), page row (0-7).
 * scale 1 = 5x7, scale 2 = 10x14. */
void oled_text(int x, int page, const char *str, int scale);
/* Filled horizontal bar on one page row, clipped to display width. */
void oled_bar(int page, int width);
/* Vertical bar rising from the bottom edge, h in pixels (0..64). */
void oled_vbar(int x, int h);
void oled_flush(void);
