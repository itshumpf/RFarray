/* telemetry — binary frame protocol v2.
 *
 * Common header (little-endian):
 *   C5 52 | type u8 | node_id u8 | env_id u16 | boot_ts_us u32 | len u16
 * then `len` payload bytes, then one XOR checksum byte covering every
 * byte after the magic (header fields + payload).
 *
 * boot_ts_us is microseconds since node start (u32, wraps every ~71 min;
 * the host unwraps — frames are far more frequent than the wrap). Using
 * node-side time keeps the series immune to serial/host latency jitter.
 *
 * type 1 (CSI) payload:
 *   seq u32 | mac[6] | rssi i8 | noise i8 | chan u8 | dropped u16 | csi[...]
 *   `dropped` is the node's cumulative queue-overflow count: any increase
 *   between consecutive frames tells the host exactly how many samples
 *   were lost (the missing-frame indicator; seq gaps give the same for
 *   RF loss).
 *
 * type 2 (STATUS) payload (emitted every few seconds):
 *   fw_ver u8 | reset_reason u8 | cal_state u8 | crash_count u16 |
 *   cal_remaining_s u16 | uptime_s u32 | pkt_total u32 | drop_total u32 |
 *   heap_free u32 | noise_floor_cq8 i16 | rssi_avg_cq8 i16
 *   (cq8 = value * 256, signed — centi-precision dBm in two bytes)
 */
#pragma once
#include <stdint.h>

#define TLM_MAGIC0       0xC5
#define TLM_MAGIC1       0x52
#define TLM_TYPE_CSI     1
#define TLM_TYPE_STATUS  2

#define TLM_FW_VERSION   2

typedef struct {
    uint8_t  reset_reason;
    uint8_t  cal_state;
    uint16_t crash_count;
    uint16_t cal_remaining_s;
    uint32_t uptime_s;
    uint32_t pkt_total;
    uint32_t drop_total;
    uint32_t heap_free;
    int16_t  noise_floor_cq8;
    int16_t  rssi_avg_cq8;
} tlm_status_t;

void tlm_init(uint8_t node_id, uint16_t env_id);

/* Both emitters are stdout-writers: call them from ONE dedicated drain
 * task only, never from the WiFi callback path. */
void tlm_send_csi(uint32_t seq, const uint8_t mac[6], int8_t rssi,
                  int8_t noise, uint8_t channel, uint32_t boot_ts_us,
                  uint16_t dropped, const int8_t *csi, uint16_t csi_len);

void tlm_send_status(uint32_t boot_ts_us, const tlm_status_t *st);
