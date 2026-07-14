/* node_hal — hardware abstraction for field telemetry nodes.
 *
 * Owns everything that touches NVS, GPIO, UART, watchdogs, and reset
 * accounting so the processing logic in main.c stays hardware-free.
 */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

/* ---- identity (persisted in NVS namespace "node") ---- */
typedef struct {
    uint8_t  node_id;       /* default: last MAC byte */
    uint16_t env_id;        /* survey environment/site tag, default 0 */
    uint16_t cal_seconds;   /* baseline calibration window, default 300 */
} node_identity_t;

/* Call once, first thing in app_main: initializes NVS, reads the reset
 * reason, and increments the persisted crash counter if the previous
 * reset was abnormal (panic / task WDT / int WDT / brownout). */
esp_err_t hal_boot_init(void);

esp_err_t hal_identity_load(node_identity_t *out);
esp_err_t hal_identity_save(const node_identity_t *id);

uint16_t hal_crash_count(void);
uint8_t  hal_reset_reason(void);          /* esp_reset_reason() as u8 */
esp_err_t hal_crash_count_clear(void);

/* ---- safe-boot / diagnostic console ---- */
/* Sample `pin` (pulled up) for `window_ms`; true if grounded. */
bool hal_safe_boot_requested(int pin, int window_ms);

/* Drop the console to 115200 baud and run the line-based configuration
 * console (SHOW / NODE n / ENV n / CAL n / CLEARCRASH / REBOOT).
 * RF stays off. Never returns. */
void hal_diag_console(int oled_sda, int oled_scl, bool oled_rot180)
    __attribute__((noreturn));

/* ---- watchdogs ---- */
/* Task watchdog: panic (-> hardware reset) if a subscribed task stops
 * feeding for timeout_ms. */
void hal_watchdog_start(uint32_t timeout_ms);
void hal_watchdog_subscribe(void);        /* call from the task to guard */
void hal_watchdog_feed(void);

/* RF-liveness watchdog: if no frame is kicked in for silence_restart_s,
 * the RF stack is considered locked and the node hard-resets. */
void hal_rf_liveness_start(uint32_t silence_restart_s);
void hal_rf_liveness_kick(void);
