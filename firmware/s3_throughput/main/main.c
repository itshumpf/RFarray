/* s3_throughput - how many bytes per second can this ESP32-S3 sustain to
 * the PC over the native USB-Serial-JTAG peripheral?
 *
 * Why this exists
 * ---------------
 * The production collector (firmware/csi_rx) is an ESP32-D0WD behind a
 * UART bridge. Its serial link is a hard ceiling and the array is already
 * pressed against it. This project answers exactly one question and
 * refuses to answer any other: what is the sustained device->host byte
 * rate of the S3's native USB, with records shaped like the real CSI
 * workload. It does NOT show that the S3 can capture CSI at that rate;
 * the S3's WiFi path is a separate open question (docs/HANDOFF.md).
 *
 * Deliberately absent: WiFi, BLE, OLED, PSRAM, NVS, calibration,
 * watchdogs, ../common. Anything that shares the bus or the CPU would
 * confound the measurement.
 *
 * Peripheral choice
 * -----------------
 * USB-Serial-JTAG (the built-in CDC on GPIO19/20), not USB-OTG CDC.
 * The board's DIS_USB_SERIAL_JTAG eFuse is virgin, so the peripheral is
 * available. There is no baud rate on this path: it is a USB endpoint,
 * and whatever the host sets in its baud field is discarded.
 *
 * Wire format (little-endian), FIXED 269-byte records
 * ---------------------------------------------------
 *   C5 54 | type u8 | fw u8 | seq u32 | boot_ts_us u32 |
 *   payload[256] | xor u8
 *
 * The xor covers every byte after the magic (header fields + payload),
 * the same rule firmware/common/telemetry uses. The magic is C5 54,
 * distinct from the array's C5 51 (v1) and C5 52 (v2), so this stream
 * can never be mistaken for telemetry by pc/rff/protocol.py.
 *
 * Fixed size is the point: the host can lock on, and a single lost or
 * mangled byte shows up as a resync rather than a silent reframe.
 *
 *   type 1 DATA    payload = verifiable pattern, byte i = (seq + 7*i) & 0xFF.
 *                  seq increments once per DATA record. Gaps in seq are
 *                  host-side loss; a payload that survives the checksum
 *                  but not the pattern is a protocol disagreement, not a
 *                  link error. The host distinguishes the two.
 *   type 2 STATUS  payload = device-side counters (below), zero padded to
 *                  256 so every record on the wire is the same length.
 *                  seq counts STATUS records, independently of DATA.
 *
 * STATUS payload (offsets in bytes, little-endian, rest zero):
 *    0 u32 uptime_ms
 *    4 u32 data_seq            DATA records emitted so far
 *    8 u32 attempted           write attempts (DATA + STATUS)
 *   12 u32 accepted_first_try  attempts the driver took whole, without waiting
 *   16 u32 would_block         attempts the driver took ZERO bytes of
 *   20 u32 partial             attempts the driver took 1..268 bytes of
 *   24 u64 bytes_committed     total bytes handed to the driver
 *   32 u64 block_us            cumulative us spent finishing blocked writes
 *   40 u32 completion_timeouts completion write that returned nothing in time
 *   44 u32 heap_free
 *   48 u32 status_seq
 *   52 u32 tx_ring_bytes       driver TX ring size - the knob, so the host
 *                              never has to guess what it was set to
 *   56 u32 cpu_mhz
 *
 * Reading attempted vs accepted_first_try
 * ---------------------------------------
 * A LOW accepted_first_try is the expected healthy result, not a fault.
 * The CPU can build records far faster than USB can drain them, so once
 * the TX ring fills, nearly every write blocks. That is the answer to
 * "is the device or the link the bottleneck": if block_us is a large
 * fraction of wall time and accepted_first_try is near zero, the S3 is
 * waiting on USB and the measured byte rate IS the link ceiling. If
 * instead accepted_first_try stays high while the byte rate is low, the
 * firmware or the host is the slow part and the number is not a ceiling.
 *
 * Timing contract
 * ---------------
 * One task owns the peripheral. STATUS is emitted from that same task, so
 * records can never interleave. Logging is switched off before the loop
 * starts; any stray log bytes from IDF internals would land in the stream
 * and the host counts them as resync bytes rather than hiding them.
 *
 * No artificial delay anywhere in the loop. If the host stops reading,
 * the loop parks in the driver by design - device throughput is host read
 * rate, and pretending otherwise would inflate the number.
 */
#include <string.h>
#include "sdkconfig.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/usb_serial_jtag.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "esp_heap_caps.h"

#define THR_MAGIC0        0xC5
#define THR_MAGIC1        0x54
#define THR_TYPE_DATA     1
#define THR_TYPE_STATUS   2
#define THR_FW_VERSION    1

#define THR_HDR           12
#define THR_PAYLOAD       256          /* matches a beacon CSI payload */
#define THR_REC           (THR_HDR + THR_PAYLOAD + 1)     /* 269 */

/* Driver TX ring. Bigger absorbs more jitter but also hides device-side
 * backpressure, so it is reported in every STATUS record. ~7.6 records. */
#define TX_RING_BYTES     2048
#define RX_RING_BYTES     256          /* unused; driver requires a size */

/* Bounded wait used only to FINISH a record the driver already took part
 * of. Abandoning a half-written record would desync the host, so this
 * loops until complete and counts each timeout instead. */
#define COMPLETE_TIMEOUT_MS 100

#define STATUS_PERIOD_MS  1000

/* Quiet gap after the boot banner so the banner's text bytes are not
 * glued to the first record. Startup only - the loop itself never waits. */
#define STARTUP_QUIET_MS  1500

#define BLAST_CORE        1            /* leave core 0 to the USB ISR */
#define BLAST_PRIO        5
#define BLAST_STACK       4096

static const char *TAG = "s3_thr";

static uint32_t s_data_seq;
static uint32_t s_status_seq;
static uint32_t s_attempted;
static uint32_t s_accepted_first_try;
static uint32_t s_would_block;
static uint32_t s_partial;
static uint32_t s_completion_timeouts;
static uint64_t s_bytes_committed;
static uint64_t s_block_us;

static void put_u32(uint8_t *p, uint32_t v)
{
    p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24;
}
static void put_u64(uint8_t *p, uint64_t v)
{
    put_u32(p, (uint32_t)v);
    put_u32(p + 4, (uint32_t)(v >> 32));
}

/* Header + xor, in place. Payload must already be filled. */
static void frame(uint8_t *rec, uint8_t type, uint32_t seq)
{
    rec[0] = THR_MAGIC0;
    rec[1] = THR_MAGIC1;
    rec[2] = type;
    rec[3] = THR_FW_VERSION;
    put_u32(rec + 4, seq);
    put_u32(rec + 8, (uint32_t)esp_timer_get_time());

    uint8_t cks = 0;
    for (int i = 2; i < THR_HDR + THR_PAYLOAD; i++) {
        cks ^= rec[i];
    }
    rec[THR_HDR + THR_PAYLOAD] = cks;
}

/* Hand one whole record to the driver.
 *
 * The first attempt is non-blocking, so its return value is a direct
 * measurement of device-side backpressure: THR_REC means the ring had
 * room, 0 means it was full, anything between means it was nearly full.
 * Only after that measurement is taken does this block, and only to
 * finish what it started.
 */
static void push_record(const uint8_t *rec)
{
    s_attempted++;

    int n = usb_serial_jtag_write_bytes(rec, THR_REC, 0);
    if (n < 0) {
        n = 0;
    }
    if (n == THR_REC) {
        s_accepted_first_try++;
        s_bytes_committed += THR_REC;
        return;
    }
    if (n == 0) {
        s_would_block++;
    } else {
        s_partial++;
    }

    int done = n;
    int64_t t0 = esp_timer_get_time();
    while (done < THR_REC) {
        int m = usb_serial_jtag_write_bytes(rec + done, THR_REC - done,
                                            pdMS_TO_TICKS(COMPLETE_TIMEOUT_MS));
        if (m <= 0) {
            s_completion_timeouts++;   /* host is not draining; keep waiting */
            continue;
        }
        done += m;
    }
    s_block_us += (uint64_t)(esp_timer_get_time() - t0);
    s_bytes_committed += THR_REC;
}

static void emit_status(uint8_t *rec)
{
    uint8_t *pl = rec + THR_HDR;
    memset(pl, 0, THR_PAYLOAD);

    put_u32(pl + 0,  (uint32_t)(esp_timer_get_time() / 1000));
    put_u32(pl + 4,  s_data_seq);
    put_u32(pl + 8,  s_attempted);
    put_u32(pl + 12, s_accepted_first_try);
    put_u32(pl + 16, s_would_block);
    put_u32(pl + 20, s_partial);
    put_u64(pl + 24, s_bytes_committed);
    put_u64(pl + 32, s_block_us);
    put_u32(pl + 40, s_completion_timeouts);
    put_u32(pl + 44, (uint32_t)heap_caps_get_free_size(MALLOC_CAP_DEFAULT));
    put_u32(pl + 48, s_status_seq);
    put_u32(pl + 52, TX_RING_BYTES);
    put_u32(pl + 56, CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ);

    frame(rec, THR_TYPE_STATUS, s_status_seq);
    s_status_seq++;
    push_record(rec);
}

/* Sole owner of the USB peripheral. Tight loop, no vTaskDelay. */
static void blast_task(void *arg)
{
    /* Two buffers so a STATUS record never has to overwrite the DATA
     * pattern mid-flight. Static: 538 bytes, and no heap in the loop. */
    static uint8_t data_rec[THR_REC];
    static uint8_t status_rec[THR_REC];

    int64_t next_status_us = esp_timer_get_time();

    while (1) {
        int64_t now = esp_timer_get_time();
        if (now >= next_status_us) {
            next_status_us = now + (int64_t)STATUS_PERIOD_MS * 1000;
            emit_status(status_rec);
        }

        /* payload[i] = (seq + 7*i) & 0xFF - cheap, and every byte depends
         * on seq, so a stale or duplicated record cannot pass unnoticed. */
        uint8_t v = (uint8_t)s_data_seq;
        uint8_t *pl = data_rec + THR_HDR;
        for (int i = 0; i < THR_PAYLOAD; i++) {
            pl[i] = v;
            v += 7;
        }

        frame(data_rec, THR_TYPE_DATA, s_data_seq);
        s_data_seq++;
        push_record(data_rec);
    }
}

void app_main(void)
{
    usb_serial_jtag_driver_config_t cfg = {
        .tx_buffer_size = TX_RING_BYTES,
        .rx_buffer_size = RX_RING_BYTES,
    };
    ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&cfg));

    ESP_LOGI(TAG, "s3_throughput fw v%d: record %d B "
             "(hdr %d + payload %d + xor 1), tx_ring %d B, cpu %d MHz",
             THR_FW_VERSION, THR_REC, THR_HDR, THR_PAYLOAD,
             TX_RING_BYTES, CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ);
    ESP_LOGI(TAG, "magic C5 54 - NOT array telemetry. "
             "run: python pc\\throughput_test.py <PORT>");

    /* From here the stream must be binary only. Anything that still logs
     * lands in the host's resync counter, where it is visible. */
    esp_log_level_set("*", ESP_LOG_NONE);
    vTaskDelay(pdMS_TO_TICKS(STARTUP_QUIET_MS));

    xTaskCreatePinnedToCore(blast_task, "blast", BLAST_STACK, NULL,
                            BLAST_PRIO, NULL, BLAST_CORE);
}
