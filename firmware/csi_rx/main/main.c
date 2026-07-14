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
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
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

/* 0.96" SSD1306 status display (optional — headless if absent) */
#define OLED_SDA            21
#define OLED_SCL            22
#define OLED_ROTATE_180     true
#define MOTION_SC           64

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

/* Status display: calibration countdown, then live spectrum. */
static void display_task(void *arg)
{
    uint32_t prev_total = 0;
    char buf[32];

    while (1) {
        uint32_t total = s_pkt_total;
        uint32_t rate = (total - prev_total) * 4;
        prev_total = total;

        oled_clear();
        oled_text(0, 0, "CSI", 2);
        snprintf(buf, sizeof(buf), "%lu/S", (unsigned long)rate);
        oled_text(46, 0, buf, 1);
        snprintf(buf, sizeof(buf), "%dDB M%.1f", s_last_rssi, (double)s_motion);
        oled_text(46, 1, buf, 1);

        if (cal_get_state() == CAL_RUNNING) {
            snprintf(buf, sizeof(buf), "CAL %uS", cal_remaining_s());
            oled_text(0, 3, buf, 2);
            snprintf(buf, sizeof(buf), "NOISE %.1f DBM",
                     (double)cal_noise_floor());
            oled_text(0, 6, buf, 1);
        } else if (total == 0) {
            oled_text(0, 4, "WAITING FOR TX...", 1);
            snprintf(buf, sizeof(buf), "CHANNEL %d", CSI_WIFI_CHANNEL);
            oled_text(0, 6, buf, 1);
        } else {
            for (int k = 0; k < MOTION_SC; k++) {
                int h = (int)(s_amp_view[k] * 1.15f);
                if (h > 46) h = 46;
                oled_vbar(k * 2, h);
                oled_vbar(k * 2 + 1, h);
            }
            if (s_motion > 2.5f) {
                oled_text(98, 2, "MOVE", 1);
            }
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

    if (hal_safe_boot_requested(SAFE_BOOT_PIN, SAFE_BOOT_WINDOW_MS)) {
        hal_diag_console(OLED_SDA, OLED_SCL, OLED_ROTATE_180);
        /* never returns */
    }

    node_identity_t id;
    ESP_ERROR_CHECK(hal_identity_load(&id));
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
