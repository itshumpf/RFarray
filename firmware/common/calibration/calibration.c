#include "calibration.h"
#include "esp_timer.h"

/* Fast EMA while establishing the baseline, slow EMA afterwards so the
 * estimate follows thermal drift (minutes) but not traffic bursts. */
#define ALPHA_CAL    0.05f
#define ALPHA_TRACK  0.002f
#define ALPHA_RSSI   0.01f

static uint16_t s_window_s;
static int64_t  s_start_us;
static bool     s_have_noise;
static float    s_noise;
static bool     s_have_rssi;
static float    s_rssi;

void cal_start(uint16_t seconds)
{
    s_window_s = seconds;
    s_start_us = esp_timer_get_time();
    s_have_noise = false;
    s_have_rssi = false;
}

cal_state_t cal_get_state(void)
{
    if (s_window_s == 0) {
        return CAL_BYPASS;
    }
    int64_t elapsed = esp_timer_get_time() - s_start_us;
    return elapsed >= (int64_t)s_window_s * 1000000 ? CAL_DONE : CAL_RUNNING;
}

uint16_t cal_remaining_s(void)
{
    if (cal_get_state() != CAL_RUNNING) {
        return 0;
    }
    int64_t left_us = (int64_t)s_window_s * 1000000
                      - (esp_timer_get_time() - s_start_us);
    return (uint16_t)(left_us / 1000000) + 1;
}

void cal_feed(int8_t noise_floor_dbm, int8_t rssi_dbm)
{
    float a = cal_get_state() == CAL_RUNNING ? ALPHA_CAL : ALPHA_TRACK;
    if (!s_have_noise) {
        s_noise = noise_floor_dbm;
        s_have_noise = true;
    } else {
        s_noise += a * (noise_floor_dbm - s_noise);
    }
    if (!s_have_rssi) {
        s_rssi = rssi_dbm;
        s_have_rssi = true;
    } else {
        s_rssi += ALPHA_RSSI * (rssi_dbm - s_rssi);
    }
}

float cal_noise_floor(void) { return s_have_noise ? s_noise : -127.0f; }
float cal_rssi_avg(void)    { return s_have_rssi ? s_rssi : -127.0f; }

bool cal_gate_open(void)
{
    return cal_get_state() != CAL_RUNNING;
}
