#include <stdio.h>
#include <string.h>
#include "telemetry.h"

static uint8_t  s_node_id;
static uint16_t s_env_id;

void tlm_init(uint8_t node_id, uint16_t env_id)
{
    s_node_id = node_id;
    s_env_id = env_id;
}

static void put_u16(uint8_t *p, uint16_t v) { p[0] = v; p[1] = v >> 8; }
static void put_u32(uint8_t *p, uint32_t v)
{
    p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24;
}

/* Write header + payload + xor checksum as one stdout burst. */
static void emit(uint8_t type, uint32_t boot_ts_us,
                 const uint8_t *payload, uint16_t len)
{
    uint8_t hdr[12];
    hdr[0] = TLM_MAGIC0;
    hdr[1] = TLM_MAGIC1;
    hdr[2] = type;
    hdr[3] = s_node_id;
    put_u16(hdr + 4, s_env_id);
    put_u32(hdr + 6, boot_ts_us);
    put_u16(hdr + 10, len);

    uint8_t cks = 0;
    for (int i = 2; i < 12; i++) cks ^= hdr[i];
    for (int i = 0; i < len; i++) cks ^= payload[i];

    fwrite(hdr, 1, sizeof(hdr), stdout);
    fwrite(payload, 1, len, stdout);
    fwrite(&cks, 1, 1, stdout);
    fflush(stdout);
}

void tlm_send_csi(uint32_t seq, const uint8_t mac[6], int8_t rssi,
                  int8_t noise, uint8_t channel, uint32_t boot_ts_us,
                  uint16_t dropped, const int8_t *csi, uint16_t csi_len)
{
    /* payload assembled in a static buffer: single-caller contract
     * (one drain task) makes this safe and heap-free */
    static uint8_t pl[15 + 384];
    if (csi_len > 384) {
        csi_len = 384;
    }
    put_u32(pl, seq);
    memcpy(pl + 4, mac, 6);
    pl[10] = (uint8_t)rssi;
    pl[11] = (uint8_t)noise;
    pl[12] = channel;
    put_u16(pl + 13, dropped);
    memcpy(pl + 15, csi, csi_len);
    emit(TLM_TYPE_CSI, boot_ts_us, pl, 15 + csi_len);
}

void tlm_send_status(uint32_t boot_ts_us, const tlm_status_t *st)
{
    uint8_t pl[27];
    pl[0] = TLM_FW_VERSION;
    pl[1] = st->reset_reason;
    pl[2] = st->cal_state;
    put_u16(pl + 3, st->crash_count);
    put_u16(pl + 5, st->cal_remaining_s);
    put_u32(pl + 7, st->uptime_s);
    put_u32(pl + 11, st->pkt_total);
    put_u32(pl + 15, st->drop_total);
    put_u32(pl + 19, st->heap_free);
    put_u16(pl + 23, (uint16_t)st->noise_floor_cq8);
    put_u16(pl + 25, (uint16_t)st->rssi_avg_cq8);
    emit(TLM_TYPE_STATUS, boot_ts_us, pl, sizeof(pl));
}
