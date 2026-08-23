# s3_throughput

One question, one answer: **how many bytes per second can the Heltec
ESP32-S3 (`8c:fd:49:b7:b0:6c`) sustain to the PC over native USB?**

It exists to decide whether porting the CSI receiver off the D0WD +
UART-bridge collector is worth doing. It does **not** show the S3 can
capture CSI at whatever rate it measures — the radio is never switched on
here, and the S3's WiFi path has its own open questions
(`docs/HANDOFF.md`).

Nothing in this directory is shared with `csi_rx` / `csi_cfo` / `csi_tx`.
It deliberately does not use `../common` (no `node_hal`, no `telemetry`,
no `calibration`), has no WiFi, no BLE, no OLED, no PSRAM and no NVS.
Anything sharing the bus or the CPU would confound the measurement.

## State: builds, not yet flashed, never run

Written without hardware access, then **built** against ESP-IDF v5.5.4 on
2026-08-21: `s3_throughput.bin` 0x2ba00 bytes, no warnings from `main.c`,
`usb_serial_jtag_write_bytes` linked. Every line of `sdkconfig.defaults`
was accepted — the console really is on USB-Serial-JTAG and both idle-task
watchdog checks really are off (verified in the generated `sdkconfig`).

A first `idf.py flash` attempt **failed**, in the documented way — see
below. **No byte of this has run on the board, and no number it produces
has been checked against anything.**

## Build and flash

Single-target project, so there is no `build_s3/` +
`sdkconfig.defaults.s3` split the way `csi_tx` has — plain `idf.py` is
correct here.

```powershell
# IDF env (docs/HANDOFF.md, "Hard-won gotchas")
$env:IDF_TOOLS_PATH = "C:\Espressif"
$env:IDF_PYTHON_ENV_PATH = "C:\Espressif\python_env\idf5.5_py3.11_env"
. C:\Espressif\frameworks\esp-idf-v5.5.4\export.ps1

cd C:\dev\csi-array\firmware\s3_throughput
idf.py set-target esp32s3               # only needed once
idf.py build
idf.py -p COM6 --no-stub -b 115200 flash
```

**Why `--no-stub -b 115200`.** The plain `idf.py -p COM6 flash` run on
2026-08-21 connected fine — esptool identified the right board (`Chip is
ESP32-S3 (QFN56) rev v0.2`, `USB mode: USB-Serial/JTAG`, `MAC
8c:fd:49:b7:b0:6c`, `Embedded PSRAM 2MB`) — then died at exactly the step
`docs/HANDOFF.md` warns about:

```
Uploading stub...
Running stub...
Stub running...
Changing baud rate to 460800
Changed.
A fatal error occurred: The chip stopped responding.
```

That is both gotchas at once: the stub dies over ROM USB-CDC, and the
460800 rebaud is flaky. `--no-stub` skips the first, `-b 115200` skips the
second. If it still refuses, put the board in manual download mode (hold
BOOT, tap RST) and retry. Other Heltec gotchas that apply: pull the LiPo
battery when debugging (USB unplug does not reboot it and uptimes lie), a
manual RST may be needed after flash, and Arduino IDE steals COM ports.

**Flash port and data port are the same port — COM6.** That is not an
assumption: esptool reached the chip on COM6 in USB-Serial/JTAG mode, so
COM6 *is* the S3's native USB, which is what this firmware writes to. Read
the throughput stream from COM6 too.

## Run the host side

```powershell
python C:\dev\csi-array\pc\throughput_test.py COM6 --seconds 30
```

There is no baud rate to match — USB-Serial-JTAG is a USB CDC endpoint and
the host's baud field is discarded by the device.

## Wire format

Fixed **269-byte** records, little-endian:

```
C5 54 | type u8 | fw u8 | seq u32 | boot_ts_us u32 | payload[256] | xor u8
```

The xor covers every byte after the magic, the same rule
`firmware/common/telemetry` uses. Magic `C5 54` is distinct from the
array's `C5 51` (v1) and `C5 52` (v2), so this stream can never be
mistaken for telemetry by `pc/rff/protocol.py`.

- **type 1 DATA** — payload byte `i` is `(seq + 7*i) & 0xFF`. Sequence
  gaps are host-side loss; a payload that passes the checksum but not the
  pattern is a version disagreement, not a link error, and the host
  reports the two separately.
- **type 2 STATUS** — device-side counters, zero-padded to 256 so every
  record on the wire is the same length. Emitted once per second from the
  same task, so records can never interleave.

## Reading `attempted` vs `accepted_first_try`

Each record is offered to the driver **non-blocking first**, so the return
value is a direct measurement of device-side backpressure. Only then does
the firmware block, and only to finish the record it already started —
abandoning a half-written record would desync the host.

A **low** `accepted_first_try` is the expected healthy result, not a
fault. The CPU builds records far faster than USB drains them, so once the
TX ring fills nearly every write blocks. That is exactly what answers the
question:

- high `block_us` + near-zero `accepted_first_try` → the S3 is waiting on
  USB, and the measured byte rate **is** the link ceiling.
- high `accepted_first_try` while the byte rate is low → the firmware or
  the host set the pace, and the number is a **floor**, not a ceiling.

`pc/throughput_test.py` applies exactly that rule and prints which case it
landed in.

## Knobs

| `main.c` | default | effect |
|---|---|---|
| `TX_RING_BYTES` | 2048 | driver TX ring (~7.6 records). Bigger absorbs jitter but hides backpressure. Reported in every STATUS record so the host never guesses. |
| `THR_PAYLOAD` | 256 | matches a beacon's CSI payload. Changing it changes the record size and both sides must agree. |
| `STATUS_PERIOD_MS` | 1000 | 269 B/s of overhead. |
| `COMPLETE_TIMEOUT_MS` | 100 | bounded wait per completion attempt; timeouts are counted, never used to abandon a record. |
| `BLAST_CORE` | 1 | leaves core 0 to the USB ISR. |

## Things to check on the first real run

Settled by the 2026-08-21 build, so **not** open questions any more: the
`usb_serial_jtag_driver_config_t` field names compile, the console really
switched to USB-Serial-JTAG, and both `ESP_TASK_WDT_CHECK_IDLE_TASK_CPU*`
lines were accepted rather than silently dropped. **Do not copy those two
watchdog lines into `csi_rx`** — they are safe only because this firmware
does nothing else.

Still unverified, because nothing has run:

1. **That it boots at all**, and that the banner appears under
   `idf.py -p COM6 monitor`. If the board resets in a loop a few seconds
   in with reason `TASK_WDT`, the watchdog reasoning above was wrong for
   this IDF version and `CONFIG_ESP_TASK_WDT_INIT=n` is the next thing to
   try.
2. **That backpressure behaves as assumed.** The whole design rests on
   `usb_serial_jtag_write_bytes(..., 0)` returning 0 when the ring is
   full, rather than discarding. If instead it silently drops bytes, the
   host will show large sequence gaps with the device reporting no
   waiting at all — a combination the host report calls out as NOT
   LINK-BOUND.
3. **`TX_RING_BYTES = 2048` is a guess**, not a tuned value. Re-run at
   512 and at 8192; if the measured rate moves much, the ring is part of
   the answer and should be reported alongside it.
4. **The boot banner.** Two `ESP_LOGI` lines go out before logging is
   switched off, so the first run after a reset shows ~100 resync bytes on
   the host. That is expected and the host says so.
5. **A host that stops reading parks the device**, by design — device
   throughput *is* host read rate. The blast loop will sit in the driver
   rather than pretend to have sent data.
