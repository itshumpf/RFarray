#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_system.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "node_hal.h"
#include "ssd1306.h"

static const char *TAG = "node_hal";

#define NVS_NS          "node"
#define DIAG_BAUD       115200
#define DIAG_LINE_MAX   64
#define CAL_DEFAULT_S   300

static nvs_handle_t s_nvs;
static uint8_t  s_reset_reason;
static uint16_t s_crash_count;

/* ------------------------------------------------------------------ */
/* boot accounting                                                     */
/* ------------------------------------------------------------------ */

esp_err_t hal_boot_init(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }
    ESP_ERROR_CHECK(nvs_open(NVS_NS, NVS_READWRITE, &s_nvs));

    esp_reset_reason_t r = esp_reset_reason();
    s_reset_reason = (uint8_t)r;
    nvs_get_u16(s_nvs, "crash", &s_crash_count);
    if (r == ESP_RST_PANIC || r == ESP_RST_TASK_WDT ||
        r == ESP_RST_INT_WDT || r == ESP_RST_WDT || r == ESP_RST_BROWNOUT) {
        s_crash_count++;
        nvs_set_u16(s_nvs, "crash", s_crash_count);
        nvs_commit(s_nvs);
        ESP_LOGW(TAG, "abnormal reset (reason=%d), crash_count=%u",
                 r, s_crash_count);
    }
    return ESP_OK;
}

uint8_t hal_reset_reason(void) { return s_reset_reason; }
uint16_t hal_crash_count(void) { return s_crash_count; }

esp_err_t hal_crash_count_clear(void)
{
    s_crash_count = 0;
    nvs_set_u16(s_nvs, "crash", 0);
    return nvs_commit(s_nvs);
}

/* ------------------------------------------------------------------ */
/* identity                                                            */
/* ------------------------------------------------------------------ */

esp_err_t hal_identity_load(node_identity_t *out)
{
    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    out->node_id = mac[5];               /* stable per-board default */
    out->env_id = 0;
    out->cal_seconds = CAL_DEFAULT_S;
    nvs_get_u8(s_nvs, "node_id", &out->node_id);
    nvs_get_u16(s_nvs, "env_id", &out->env_id);
    nvs_get_u16(s_nvs, "cal_s", &out->cal_seconds);
    return ESP_OK;
}

esp_err_t hal_identity_save(const node_identity_t *id)
{
    nvs_set_u8(s_nvs, "node_id", id->node_id);
    nvs_set_u16(s_nvs, "env_id", id->env_id);
    nvs_set_u16(s_nvs, "cal_s", id->cal_seconds);
    return nvs_commit(s_nvs);
}

/* ------------------------------------------------------------------ */
/* safe boot + diagnostic console                                      */
/* ------------------------------------------------------------------ */

bool hal_safe_boot_requested(int pin, int window_ms)
{
    gpio_config_t io = {
        .pin_bit_mask = 1ULL << pin,
        .mode         = GPIO_MODE_INPUT,
        .pull_up_en   = GPIO_PULLUP_ENABLE,
    };
    gpio_config(&io);
    for (int t = 0; t < window_ms; t += 50) {
        if (gpio_get_level(pin) == 0) {
            return true;
        }
        vTaskDelay(pdMS_TO_TICKS(50));
    }
    return false;
}

static void diag_show(const node_identity_t *id)
{
    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    printf("node_id      : %u\n", id->node_id);
    printf("env_id       : %u\n", id->env_id);
    printf("cal_seconds  : %u\n", id->cal_seconds);
    printf("mac          : %02x:%02x:%02x:%02x:%02x:%02x\n",
           mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    printf("reset_reason : %u\n", s_reset_reason);
    printf("crash_count  : %u\n", s_crash_count);
    printf("uptime_s     : %llu\n",
           (unsigned long long)(esp_timer_get_time() / 1000000));
}

static void diag_help(void)
{
    printf("commands: SHOW | NODE <0-255> | ENV <0-65535> | "
           "CAL <seconds, 0=off> | CLEARCRASH | REBOOT | HELP\n");
}

void hal_diag_console(int oled_sda, int oled_scl, bool oled_rot180)
{
    printf("\nSAFE BOOT: dropping console to %d baud\n", DIAG_BAUD);
    fflush(stdout);
    uart_wait_tx_idle_polling(UART_NUM_0);
    uart_set_baudrate(UART_NUM_0, DIAG_BAUD);
    /* driver install gives us buffered RX for the console input */
    uart_driver_install(UART_NUM_0, 512, 0, 0, NULL, 0);

    if (oled_init(oled_sda, oled_scl, oled_rot180) == ESP_OK) {
        oled_clear();
        oled_text(0, 0, "SAFE BOOT", 2);
        oled_text(0, 4, "DIAG CONSOLE 115200", 1);
        oled_text(0, 6, "RF OFF", 1);
        oled_flush();
    }

    node_identity_t id;
    hal_identity_load(&id);
    printf("diagnostic console ready. RF off.\n");
    diag_help();
    printf("> ");
    fflush(stdout);

    char line[DIAG_LINE_MAX];
    int  pos = 0;
    while (1) {
        uint8_t c;
        int n = uart_read_bytes(UART_NUM_0, &c, 1, pdMS_TO_TICKS(100));
        if (n <= 0) {
            continue;
        }
        if (c == '\r' || c == '\n') {
            if (pos == 0) {
                continue;
            }
            line[pos] = 0;
            pos = 0;
            unsigned v;
            if (!strcasecmp(line, "SHOW")) {
                diag_show(&id);
            } else if (sscanf(line, "NODE %u", &v) == 1 && v <= 255) {
                id.node_id = (uint8_t)v;
                hal_identity_save(&id);
                printf("node_id=%u saved\n", id.node_id);
            } else if (sscanf(line, "ENV %u", &v) == 1 && v <= 65535) {
                id.env_id = (uint16_t)v;
                hal_identity_save(&id);
                printf("env_id=%u saved\n", id.env_id);
            } else if (sscanf(line, "CAL %u", &v) == 1 && v <= 65535) {
                id.cal_seconds = (uint16_t)v;
                hal_identity_save(&id);
                printf("cal_seconds=%u saved\n", id.cal_seconds);
            } else if (!strcasecmp(line, "CLEARCRASH")) {
                hal_crash_count_clear();
                printf("crash_count=0\n");
            } else if (!strcasecmp(line, "REBOOT")) {
                printf("rebooting\n");
                fflush(stdout);
                uart_wait_tx_idle_polling(UART_NUM_0);
                esp_restart();
            } else {
                diag_help();
            }
            printf("> ");
            fflush(stdout);
        } else if (pos < DIAG_LINE_MAX - 1 && c >= 0x20 && c < 0x7f) {
            line[pos++] = (char)c;
        }
    }
}

/* ------------------------------------------------------------------ */
/* watchdogs                                                           */
/* ------------------------------------------------------------------ */

void hal_watchdog_start(uint32_t timeout_ms)
{
    esp_task_wdt_config_t cfg = {
        .timeout_ms    = timeout_ms,
        .idle_core_mask = 0,
        .trigger_panic = true,           /* panic -> hardware reset */
    };
    esp_err_t err = esp_task_wdt_init(&cfg);
    if (err == ESP_ERR_INVALID_STATE) {  /* already running: retune it */
        err = esp_task_wdt_reconfigure(&cfg);
    }
    ESP_ERROR_CHECK(err);
}

void hal_watchdog_subscribe(void)
{
    ESP_ERROR_CHECK(esp_task_wdt_add(NULL));
}

void hal_watchdog_feed(void)
{
    esp_task_wdt_reset();
}

static volatile int64_t s_last_rf_us;
static uint32_t s_silence_limit_us;

static void rf_liveness_check(void *arg)
{
    int64_t silent = esp_timer_get_time() - s_last_rf_us;
    if (silent > (int64_t)s_silence_limit_us) {
        ESP_LOGE(TAG, "RF silent for %lld us (limit %lu) — "
                 "assuming stack lock, restarting",
                 silent, (unsigned long)s_silence_limit_us);
        esp_restart();
    }
}

void hal_rf_liveness_start(uint32_t silence_restart_s)
{
    s_silence_limit_us = silence_restart_s * 1000000u;
    s_last_rf_us = esp_timer_get_time();
    const esp_timer_create_args_t args = {
        .callback = rf_liveness_check,
        .name     = "rf_live",
    };
    esp_timer_handle_t h;
    ESP_ERROR_CHECK(esp_timer_create(&args, &h));
    ESP_ERROR_CHECK(esp_timer_start_periodic(h, 5 * 1000000));
}

void hal_rf_liveness_kick(void)
{
    s_last_rf_us = esp_timer_get_time();
}
