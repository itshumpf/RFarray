/* calibration — startup baseline + slow thermal tracking of the local
 * noise floor.
 *
 * Audit protocol: for the first `seconds` after start the node is in
 * CAL_RUNNING — it samples the ambient noise floor of every received
 * frame into a fast EMA and does NOT report signal events. After the
 * window closes (CAL_DONE) the estimate keeps updating with a much
 * slower EMA so it follows thermal drift in the field without letting
 * short-lived interference rewrite the baseline. seconds=0 disables the
 * gate entirely (bench mode, CAL_BYPASS).
 */
#pragma once
#include <stdint.h>
#include <stdbool.h>

typedef enum {
    CAL_RUNNING = 0,     /* baseline window open — hold CSI reporting */
    CAL_DONE    = 1,     /* baseline locked, slow tracking active */
    CAL_BYPASS  = 2,     /* calibration disabled (cal_seconds == 0) */
} cal_state_t;

void        cal_start(uint16_t seconds);
/* Feed every received frame's noise floor + RSSI (both dBm). */
void        cal_feed(int8_t noise_floor_dbm, int8_t rssi_dbm);
cal_state_t cal_get_state(void);
uint16_t    cal_remaining_s(void);
float       cal_noise_floor(void);   /* EMA estimate, dBm */
float       cal_rssi_avg(void);      /* EMA of received RSSI, dBm */
/* True when CSI/telemetry reporting is allowed (DONE or BYPASS). */
bool        cal_gate_open(void);
