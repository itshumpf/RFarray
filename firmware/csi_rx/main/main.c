/* csi_rx — field telemetry node (fw v2).
 *
 * Captures CSI for frames on a fixed channel and streams binary v2
 * telemetry over USB serial (see telemetry.h for the frame layout).
 *
 * Field-hardening layout:
 *   node_hal      identity/NVS, crash accounting, safe-boot console,
 *                 task watchdog + RF-liveness watchdog, OLED driver
 *   calibration   startup baseline noise-floor cycle + thermal tracking
 *   telemetry     v2 frame builder (node/env IDs, boot-relative time,
 *                 cumulative-drop indicator, periodic STATUS frames)
 *   main.c        wiring only — no direct NVS/UART/WDT access here
 *
 * Timing contract: the CSI callback runs in WiFi task context and only
 * copies into a queue (non-blocking, zero serial I/O). One drain task
 * owns stdout. Sampling cadence is therefore set by RF arrivals alone,
 * never by host serial latency.
 */
#include <string.h>
#include <stdio.h>
#include <stdarg.h>
#include "sdkconfig.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "driver/gpio.h"
#include "esp_wifi.h"
#include "esp_now.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include <math.h>

#include "node_hal.h"
#include "telemetry.h"
#include "calibration.h"
#include "ssd1306.h"

#define CSI_WIFI_CHANNEL    6          /* must match csi_tx */

/* RFF capture mode: 1 = promiscuous sniffing so CSI fires for EVERY
 * decodable frame on the channel, 0 = only frames the node would
 * normally receive (clean beacon stream). */
#define RFF_PROMISCUOUS     1
#define CSI_BUF_MAX         384
#define QUEUE_DEPTH         64

/* Safe-Boot: hold BOOT (GPIO0) low while the app starts -> diagnostic
 * console at 115200, RF off. GPIO0 low during RESET enters the ROM
 * downloader instead — release EN first, then hold BOOT. */
#define SAFE_BOOT_PIN       0
#define SAFE_BOOT_WINDOW_MS 500

/* Watchdogs: drain task must run every WDT_TIMEOUT_MS; a hardware reset
 * fires if the RF stack delivers nothing for RF_SILENCE_RESTART_S. */
#define WDT_TIMEOUT_MS      10000
#define RF_SILENCE_RESTART_S 120

#define STATUS_PERIOD_MS    5000

/* ------------------------------------------------------------------ *
 * 0.96" SSD1306 status display (optional — headless if absent)
 *
 * csi_rx builds for BOTH the original ESP32 D0WD desk node and the
 * Heltec ESP32-S3, and the two panels are wired completely differently.
 * Everything in this block is target-conditional. The D0WD values are
 * the ones this file has always carried and are unchanged; the #else
 * branch is what that build sees, byte for byte.
 *
 * ESP32-S3 numbers below were MEASURED by firmware/i2c_scan on the
 * benched Heltec (board MAC 8c:fd:49:b7:b0:6c), 2026-08-22. They are
 * observations from that run, not a datasheet or a vendor pinout:
 *
 *   SDA = GPIO17, SCL = GPIO18, address 0x3C. 0x3C was the only address
 *     that ever answered; nothing else sits on that bus.
 *
 *   The old OLED_SCL 22 cannot work here: GPIO22 does not exist on the
 *     ESP32-S3 and gpio_config() returns a GPIO_PIN mask error for it.
 *     That is why this panel has never come up on the S3.
 *
 *   Vext = GPIO36, driven LOW. i2c_scan's auto-generated summary line
 *     says "rail state didn't matter" — that verdict is too strong and
 *     is not what the per-state detail shows. With Vext LOW the bus is
 *     idle and the panel ACKs with or without a reset pulse. With Vext
 *     HIGH or FLOATING, GPIO17 reads 0 with a pullup on it (line held
 *     low, pair skipped) and it only ACKs after GPIO21 is pulsed. LOW
 *     is the clean state, so LOW is what we drive.
 *
 *   RST_OLED = GPIO21. Pulsing it low ~10 ms then releasing frees the
 *     bus in the non-LOW rail states. With Vext already LOW it is not
 *     required, but it costs 160 ms once at boot and removes a whole
 *     class of bring-up failure, so we do it anyway. GPIO21 is not a
 *     bus pin in this configuration, so there is no conflict.
 * ------------------------------------------------------------------ */
#if CONFIG_IDF_TARGET_ESP32S3
#define OLED_SDA            17
#define OLED_SCL            18
#define OLED_VEXT_GPIO      36     /* switched 3V3 rail; ON = driven LOW */
#define OLED_RST_GPIO       21     /* RST_OLED, active low */
#define OLED_VEXT_SETTLE_MS 300    /* rail rise + panel power-on; i2c_scan's */
#define OLED_RST_LOW_MS     10     /* SSD1306 needs >3 us; 10 ms is free */
#define OLED_RST_SETTLE_MS  150
#else                              /* ESP32 D0WD desk node — do not change */
#define OLED_SDA            21
#define OLED_SCL            22
#endif
#define OLED_ROTATE_180     true
#define MOTION_SC           64

/* Display layout: 5x7 font on a 6x8 cell => 21 chars x 8 page-rows.
 *   page 0     node id, uptime, calibration state ( + MOVE flag )
 *   page 1     frames/sec, cumulative drops, distinct MAC count
 *   page 2     per-beacon RSSI
 *   page 3     cadence warning / waiting-for-TX hint (blank when healthy)
 *   pages 4-7  live amplitude band, 64 subcarriers x 2 px, 32 px tall
 *
 * The band is on the BOTTOM half on purpose. oled_vbar() is anchored to
 * the bottom edge and has no upper clip (common/node_hal/ssd1306.c), so
 * a bottom-half band needs no new driver primitive — clamping the height
 * to 32 is the whole implementation. That keeps this change inside
 * csi_rx and leaves node_hal (and therefore csi_cfo) untouched. */
#define DISP_COLS           21
#define DISP_LINE_BUF       (DISP_COLS + 1)
#define BAND_H              32     /* pixels; pages 4..7 */
/* Original full-height band used amp * 1.15 clipped at 46 px. Scaling
 * that same dynamic range into 32 px: 1.15 * (32/46) = 0.80. */
#define BAND_SCALE          0.80f
#define MOTION_MOVE_THRESH  2.5f

/* Per-source accounting. main.c previously tracked only s_pkt_total and
 * s_last_rssi, which cannot answer "is B1 still on cadence" — the thing
 * that went unnoticed on 2026-08-22 when B1 sat at 6.47 fps. This is the
 * minimum state added: one fixed-size table, no allocation, one linear
 * scan per drained frame.
 *
 * Slots 0..2 are permanently reserved for the three expected beacons so
 * ambient traffic can never evict them (RFF_PROMISCUOUS is 1, so CSI
 * fires for every decodable frame on the channel and ambient MACs are
 * plentiful). The MAC list mirrors pc/occ/__init__.py BEACON_MACS; this
 * is the display's own copy of it, not an import, and it will go stale
 * if that file changes. */
#define BEACON_N            3
#define MAC_TABLE_MAX       24
/* pc/node_census.py BEACON_MIN_FPS = 10.0, per docs/LOT_HYPOTHESIS.md
 * section 3. Same floor pc/diagnose.py checks after the fact; this puts
 * it on the device, live. Held as tenths to keep the compare integral. */
#define BEACON_MIN_FPS_X10  100

/* Optional hard filter on the TX beacon MAC; all-zero accepts any. */
static const uint8_t TX_FILTER_MAC[6] = {0, 0, 0, 0, 0, 0};

static const char *TAG = "csi_rx";

typedef struct {
    uint32_t seq;
    uint8_t  mac[6];
    int8_t   rssi;
    int8_t   noise_floor;
    uint8_t  channel;
    uint32_t timestamp;               /* us since node start (WiFi clock) */
    uint16_t len;
    int8_t   buf[CSI_BUF_MAX];
} csi_sample_t;

static QueueHandle_t s_csi_queue;
static volatile uint32_t s_latest_seq = 0;
static volatile uint16_t s_dropped = 0;       /* cumulative, wraps u16 */

/* display-shared stats (single writer per field) */
static volatile uint32_t s_pkt_total = 0;
static volatile int      s_last_rssi = 0;
static volatile float    s_motion = 0.0f;
static float s_amp_view[MOTION_SC];
static uint8_t s_node_id = 0;                 /* set once, before tasks start */

/* Expected beacons. Order fixes the reserved slot index. */
static const uint8_t BEACON_MAC[BEACON_N][6] = {
    {0xa4, 0xf0, 0x0f, 0x77, 0x91, 0x20},     /* B1 reference, wall outlet */
    {0x28, 0x05, 0xa5, 0x2f, 0xfa, 0x48},     /* B2 */
    {0xf4, 0x2d, 0xc9, 0x70, 0x72, 0x30},     /* B3 */
};
static const char *const BEACON_NAME[BEACON_N] = {"B1", "B2", "B3"};

typedef struct {
    uint8_t  mac[6];
    bool     used;
    volatile int8_t   rssi;    /* most recent */
    volatile uint32_t count;   /* frames drained since boot */
} mac_slot_t;

/* Writer: csi_drain_task only. Reader: display_task only.
 * No lock. `count` and `rssi` are single aligned words, so a reader sees
 * either the old or the new value, never a blend. The one true race is
 * an ambient slot being claimed while the display counts slots: `used`
 * may be visible before `mac`/`count`. That is harmless here because the
 * display never renders a MAC — the worst outcome is the distinct-MAC
 * count reading one high for a single 250 ms frame. Slots 0..2 are
 * filled before any task exists, so the beacon rows never race at all. */
static mac_slot_t s_macs[MAC_TABLE_MAX];
static volatile bool s_mac_overflow = false;

static void source_table_init(void)
{
    for (int i = 0; i < BEACON_N; i++) {
        memcpy(s_macs[i].mac, BEACON_MAC[i], 6);
        s_macs[i].used  = true;
        s_macs[i].count = 0;      /* 0 == never heard, rendered as "--" */
        s_macs[i].rssi  = 0;
    }
}

/* Called from the drain task, once per frame. Bounded work: at most
 * MAC_TABLE_MAX 6-byte memcmps, no allocation, no blocking. */
static void record_source(const uint8_t mac[6], int8_t rssi)
{
    for (int i = 0; i < MAC_TABLE_MAX; i++) {
        if (s_macs[i].used && memcmp(s_macs[i].mac, mac, 6) == 0) {
            s_macs[i].rssi = rssi;
            s_macs[i].count++;
            return;
        }
    }
    for (int i = BEACON_N; i < MAC_TABLE_MAX; i++) {
        if (!s_macs[i].used) {
            memcpy(s_macs[i].mac, mac, 6);
            s_macs[i].rssi  = rssi;
            s_macs[i].count = 1;
            s_macs[i].used  = true;
            return;
        }
    }
    /* Table full. The displayed distinct count becomes a lower bound and
     * is marked "+" so it is never mistaken for a complete census; the
     * authoritative one is pc/mac_census.py over the captured CSV. */
    s_mac_overflow = true;
}

/* ESP-NOW receive callback: extract beacon sequence number. */
static void espnow_recv_cb(const esp_now_recv_info_t *info,
                           const uint8_t *data, int len)
{
    if (len >= 8) {
        uint32_t magic;
        memcpy(&magic, data, 4);
        if (magic == 0xC51C51C5) {
            uint32_t seq;
            memcpy(&seq, data + 4, 4);
            s_latest_seq = seq;
        }
    }
}

/* CSI callback: WiFi task context — copy out fast, never block. */
static void csi_rx_cb(void *ctx, wifi_csi_info_t *info)
{
    if (!info || !info->buf || info->len == 0) {
        return;
    }
    if (TX_FILTER_MAC[0] | TX_FILTER_MAC[1] | TX_FILTER_MAC[2] |
        TX_FILTER_MAC[3] | TX_FILTER_MAC[4] | TX_FILTER_MAC[5]) {
        if (memcmp(info->mac, TX_FILTER_MAC, 6) != 0) {
            return;
        }
    }

    csi_sample_t s;
    s.seq = s_latest_seq;
    memcpy(s.mac, info->mac, 6);
    s.rssi        = info->rx_ctrl.rssi;
    s.noise_floor = info->rx_ctrl.noise_floor;
    s.channel     = info->rx_ctrl.channel;
    s.timestamp   = info->rx_ctrl.timestamp;
    s.len         = info->len > CSI_BUF_MAX ? CSI_BUF_MAX : info->len;
    memcpy(s.buf, info->buf, s.len);

    if (xQueueSend(s_csi_queue, &s, 0) != pdTRUE) {
        s_dropped++;                   /* counted, reported in-band */
    }
}

/* Motion metric: mean abs diff of LLTF amplitudes vs previous frame. */
static void update_motion(const csi_sample_t *s)
{
    static float prev[MOTION_SC];
    static bool have_prev = false;

    if (s->len < MOTION_SC * 2) {
        return;
    }
    float amp[MOTION_SC];
    for (int k = 0; k < MOTION_SC; k++) {
        float im = s->buf[2 * k];
        float re = s->buf[2 * k + 1];
        amp[k] = sqrtf(im * im + re * re);
    }
    if (have_prev) {
        float acc = 0;
        for (int k = 0; k < MOTION_SC; k++) {
            acc += fabsf(amp[k] - prev[k]);
        }
        s_motion = 0.7f * s_motion + 0.3f * (acc / MOTION_SC);
    }
    memcpy(prev, amp, sizeof(prev));
    memcpy(s_amp_view, amp, sizeof(s_amp_view));
    have_prev = true;
}

/* Drain task: sole owner of stdout. Bounded-wait receive keeps the task
 * watchdog fed even on a silent channel. */
static void csi_drain_task(void *arg)
{
    csi_sample_t s;
    hal_watchdog_subscribe();
    while (1) {
        hal_watchdog_feed();
        if (xQueueReceive(s_csi_queue, &s, pdMS_TO_TICKS(250)) != pdTRUE) {
            continue;
        }
        hal_rf_liveness_kick();
        s_pkt_total++;
        s_last_rssi = s.rssi;
        record_source(s.mac, s.rssi);
        cal_feed(s.noise_floor, s.rssi);
        update_motion(&s);
        if (cal_gate_open()) {
            tlm_send_csi(s.seq, s.mac, s.rssi, s.noise_floor, s.channel,
                         s.timestamp, s_dropped, s.buf, s.len);
        }
    }
}

/* Periodic STATUS frame: node health in-band on the same stream. */
static void status_task(void *arg)
{
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(STATUS_PERIOD_MS));
        tlm_status_t st = {
            .reset_reason    = hal_reset_reason(),
            .cal_state       = (uint8_t)cal_get_state(),
            .crash_count     = hal_crash_count(),
            .cal_remaining_s = cal_remaining_s(),
            .uptime_s        = (uint32_t)(esp_timer_get_time() / 1000000),
            .pkt_total       = s_pkt_total,
            .drop_total      = s_dropped,
            .heap_free       = (uint32_t)heap_caps_get_free_size(MALLOC_CAP_DEFAULT),
            .noise_floor_cq8 = (int16_t)(cal_noise_floor() * 256.0f),
            .rssi_avg_cq8    = (int16_t)(cal_rssi_avg() * 256.0f),
        };
        tlm_send_status((uint32_t)esp_timer_get_time(), &st);
    }
}

/* Panel power/reset sequence. Must run before any oled_init() — both the
 * normal path and the safe-boot diagnostic console call oled_init(). */
#if CONFIG_IDF_TARGET_ESP32S3
static void oled_panel_power_up(void)
{
    gpio_config_t vext = {
        .pin_bit_mask = 1ULL << OLED_VEXT_GPIO,
        .mode         = GPIO_MODE_OUTPUT,
        .pull_up_en   = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    gpio_reset_pin((gpio_num_t)OLED_VEXT_GPIO);
    gpio_config(&vext);
    gpio_set_level((gpio_num_t)OLED_VEXT_GPIO, 0);      /* rail ON */
    vTaskDelay(pdMS_TO_TICKS(OLED_VEXT_SETTLE_MS));

    gpio_config_t rst = {
        .pin_bit_mask = 1ULL << OLED_RST_GPIO,
        .mode         = GPIO_MODE_OUTPUT,
        .pull_up_en   = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    gpio_reset_pin((gpio_num_t)OLED_RST_GPIO);
    gpio_config(&rst);
    gpio_set_level((gpio_num_t)OLED_RST_GPIO, 0);
    vTaskDelay(pdMS_TO_TICKS(OLED_RST_LOW_MS));
    gpio_set_level((gpio_num_t)OLED_RST_GPIO, 1);       /* released */
    vTaskDelay(pdMS_TO_TICKS(OLED_RST_SETTLE_MS));
    /* GPIO21 is left driven high. It is not a bus pin in this wiring. */
}
#else
/* D0WD desk node: the panel is on the always-on 3V3 rail and has no
 * software-controlled reset. Deliberately a no-op so that build is
 * behaviourally identical to before this change. */
static void oled_panel_power_up(void) { }
#endif

/* snprintf with a cursor that can never run past the buffer. Note that
 * snprintf returns the length it WOULD have written, so appending with a
 * raw running offset silently walks off the end on truncation. */
static int line_cat(char *dst, size_t cap, int at, const char *fmt, ...)
{
    if (at < 0) {
        at = 0;
    }
    if ((size_t)at >= cap - 1) {
        return (int)cap - 1;
    }
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(dst + at, cap - at, fmt, ap);
    va_end(ap);
    if (n < 0) {
        return at;
    }
    at += n;
    if ((size_t)at > cap - 1) {
        at = (int)cap - 1;
    }
    return at;
}

/* Status display. See the layout comment at the top of this file.
 *
 * Drain-path contract: this task is priority 3, csi_drain_task is
 * priority 5, so the preemptive scheduler puts the drain in front of
 * every part of this function including the blocking I2C write. Nothing
 * here is shared with the drain path under a lock, and nothing here
 * touches the CSI queue, stdout or the WiFi stack. */
static void display_task(void *arg)
{
    static uint32_t prev_total = 0;
    static uint32_t prev_count[BEACON_N];
    static uint32_t fps_total = 0;
    static uint32_t beacon_fps_x10[BEACON_N];
    bool have_rates = false;
    int  tick = 0;
    char line[DISP_LINE_BUF];

    while (1) {
        /* Rates over a full second, recomputed every 4th refresh. A
         * 250 ms delta of a ~175 fps stream quantizes to ±4 fps, which
         * is far too coarse to compare against a 10 fps floor. */
        if (++tick >= 4) {
            tick = 0;
            uint32_t total = s_pkt_total;
            fps_total  = total - prev_total;
            prev_total = total;
            for (int i = 0; i < BEACON_N; i++) {
                uint32_t c = s_macs[i].count;
                beacon_fps_x10[i] = (c - prev_count[i]) * 10;
                prev_count[i] = c;
            }
            have_rates = true;
        }

        cal_state_t st = cal_get_state();
        uint32_t up = (uint32_t)(esp_timer_get_time() / 1000000);
        /* Hours clamped so the row can never grow past its column
         * budget. A >99 h uptime is a >4 day run; the authoritative
         * uptime is uptime_s in the STATUS telemetry frame, not here. */
        uint32_t uh = up / 3600;
        if (uh > 99) {
            uh = 99;
        }

        oled_clear();

        /* --- page 0: identity, uptime, calibration ------------------ */
        int n = line_cat(line, sizeof(line), 0, "N%u %02u:%02u:%02u ",
                         (unsigned)s_node_id, (unsigned)uh,
                         (unsigned)((up / 60) % 60), (unsigned)(up % 60));
        if (st == CAL_RUNNING) {
            unsigned rem = cal_remaining_s();
            if (rem > 999) {
                n = line_cat(line, sizeof(line), n, "C%uM", rem / 60);
            } else {
                n = line_cat(line, sizeof(line), n, "C%uS", rem);
            }
        } else {
            n = line_cat(line, sizeof(line), n,
                         (st == CAL_BYPASS) ? "BYP" : "RDY");
        }
        oled_text(0, 0, line, 1);
        /* MOVE sits in the last 4 cells of page 0. Only drawn outside
         * calibration, where the countdown owns that space. */
        if (st != CAL_RUNNING && s_motion > MOTION_MOVE_THRESH) {
            oled_text(104, 0, "MOVE", 1);
        }

        /* --- page 1: throughput, drops, distinct sources ------------ */
        int distinct = 0;
        for (int i = 0; i < MAC_TABLE_MAX; i++) {
            if (s_macs[i].used && s_macs[i].count) {
                distinct++;
            }
        }
        /* s_dropped is a cumulative u16 and wraps; it is the same value
         * the STATUS frame carries, so host and panel agree. */
        line_cat(line, sizeof(line), 0, "%luF/S D%u M%d%s",
                 (unsigned long)fps_total, (unsigned)s_dropped, distinct,
                 s_mac_overflow ? "+" : "");
        oled_text(0, 1, line, 1);

        /* --- page 2: per-beacon RSSI -------------------------------- */
        n = 0;
        for (int i = 0; i < BEACON_N; i++) {
            n = line_cat(line, sizeof(line), n, "%s%s",
                         i ? " " : "", BEACON_NAME[i]);
            if (s_macs[i].count) {
                n = line_cat(line, sizeof(line), n, "%4d",
                             (int)s_macs[i].rssi);
            } else {
                n = line_cat(line, sizeof(line), n, "  --");
            }
        }
        oled_text(0, 2, line, 1);

        /* --- page 3: cadence warning, else blank -------------------- */
        if (s_pkt_total == 0) {
            line_cat(line, sizeof(line), 0, "WAITING FOR TX CH%d",
                     CSI_WIFI_CHANNEL);
            oled_text(0, 3, line, 1);
        } else if (have_rates) {
            /* Only beacons that have actually been heard are checked. A
             * beacon that has never transmitted already reads "--" on
             * page 2; calling that "below the floor" would conflate
             * "slow" with "absent". */
            n = 0;
            for (int i = 0; i < BEACON_N; i++) {
                if (!s_macs[i].count) {
                    continue;
                }
                if (beacon_fps_x10[i] >= BEACON_MIN_FPS_X10) {
                    continue;
                }
                /* "!B1 6.0" then " B2 2.0"... — 7 cells each, so all
                 * three slow beacons still fit the 21-cell row. */
                n = line_cat(line, sizeof(line), n, "%s%s %u.%u",
                             (n == 0) ? "!" : " ", BEACON_NAME[i],
                             (unsigned)(beacon_fps_x10[i] / 10),
                             (unsigned)(beacon_fps_x10[i] % 10));
            }
            if (n) {
                /* Name the floor only when there is room left for it;
                 * with all three slow the rates themselves fill the row
                 * and the floor is the one thing that never changes. */
                if (n <= DISP_COLS - 4) {
                    line_cat(line, sizeof(line), n, " <%u",
                             (unsigned)(BEACON_MIN_FPS_X10 / 10));
                }
                oled_text(0, 3, line, 1);
            } else if (st == CAL_RUNNING) {
                /* Nothing to warn about and the baseline window is still
                 * open: reuse the row for the noise floor, which the old
                 * layout showed and this one otherwise loses.
                 * Rendered from integer tenths on purpose — the previous
                 * code used "%.1f", which silently prints nothing useful
                 * if CONFIG_NEWLIB_NANO_FORMAT is ever turned on. */
                int nf10 = (int)(cal_noise_floor() * 10.0f);
                int frac = nf10 % 10;
                line_cat(line, sizeof(line), 0, "NOISE %d.%dDBM",
                         nf10 / 10, frac < 0 ? -frac : frac);
                oled_text(0, 3, line, 1);
            }
        }

        /* --- pages 4..7: live amplitude band ------------------------ */
        for (int k = 0; k < MOTION_SC; k++) {
            int h = (int)(s_amp_view[k] * BAND_SCALE);
            if (h > BAND_H) {
                h = BAND_H;
            } else if (h < 1 && s_amp_view[k] > 0.0f) {
                h = 1;              /* a live-but-tiny bin stays visible */
            }
            oled_vbar(k * 2, h);
            oled_vbar(k * 2 + 1, h);
        }

        oled_flush();
        vTaskDelay(pdMS_TO_TICKS(250));
    }
}

static void wifi_init(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
#if RFF_PROMISCUOUS
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));
#endif
    ESP_ERROR_CHECK(esp_wifi_set_channel(CSI_WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE));
}

static void csi_init(void)
{
    wifi_csi_config_t csi_cfg = {
        .lltf_en           = true,
        .htltf_en          = true,
        .stbc_htltf2_en    = true,
        .ltf_merge_en      = true,
        .channel_filter_en = false,
        .manu_scale        = false,
        .shift             = 0,
    };
    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi_cfg));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(csi_rx_cb, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));
}

void app_main(void)
{
    ESP_ERROR_CHECK(hal_boot_init());

    /* Power and reset the panel before anything can call oled_init() —
     * the safe-boot console below is one of those callers. No-op on the
     * D0WD. */
    oled_panel_power_up();

    if (hal_safe_boot_requested(SAFE_BOOT_PIN, SAFE_BOOT_WINDOW_MS)) {
        /* NOTE (2026-08-22, S3 only, deliberately not fixed in this
         * pass): hal_diag_console() is hard-coded to UART_NUM_0
         * (common/node_hal/node_hal.c) — it re-baudrates UART0, installs
         * the UART driver on it, and reads the operator's commands from
         * it. sdkconfig.defaults.esp32s3 moved this build's console to
         * USB-Serial-JTAG, so on the S3 that text now goes out a pin
         * nobody reads and the console accepts no input. The OLED half
         * of the diagnostic screen below still works, and that is all
         * safe boot gives you on the S3 today. Tracked as a V2
         * prerequisite in docs/V2_SPEC.md; out of scope here. The D0WD
         * is unaffected — its console is UART0. */
        hal_diag_console(OLED_SDA, OLED_SCL, OLED_ROTATE_180);
        /* never returns */
    }

    node_identity_t id;
    ESP_ERROR_CHECK(hal_identity_load(&id));
    s_node_id = id.node_id;
    source_table_init();
    tlm_init(id.node_id, id.env_id);
    cal_start(id.cal_seconds);
    ESP_LOGI(TAG, "node_id=%u env_id=%u cal=%us reset_reason=%u crashes=%u",
             id.node_id, id.env_id, id.cal_seconds,
             hal_reset_reason(), hal_crash_count());

    /* Display first so calibration progress shows during bring-up.
     * Headless-first: non-fatal if the OLED is missing. */
    if (oled_init(OLED_SDA, OLED_SCL, OLED_ROTATE_180) == ESP_OK) {
        xTaskCreate(display_task, "display", 4096, NULL, 3, NULL);
    } else {
        ESP_LOGW(TAG, "OLED not found on SDA=%d SCL=%d — running headless",
                 OLED_SDA, OLED_SCL);
    }

    wifi_init();

    ESP_ERROR_CHECK(esp_now_init());
    ESP_ERROR_CHECK(esp_now_register_recv_cb(espnow_recv_cb));

    s_csi_queue = xQueueCreate(QUEUE_DEPTH, sizeof(csi_sample_t));
    configASSERT(s_csi_queue);

    hal_watchdog_start(WDT_TIMEOUT_MS);
    xTaskCreate(csi_drain_task, "csi_drain", 8192, NULL, 5, NULL);
    xTaskCreate(status_task, "status", 4096, NULL, 4, NULL);

    csi_init();
    hal_rf_liveness_start(RF_SILENCE_RESTART_S);

    uint8_t mac[6];
    ESP_ERROR_CHECK(esp_wifi_get_mac(WIFI_IF_STA, mac));
    ESP_LOGI(TAG, "node MAC " MACSTR " listening on ch %d",
             MAC2STR(mac), CSI_WIFI_CHANNEL);
}
