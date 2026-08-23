# S3_LINK_PATH — where CSI frames actually leave the Heltec ESP32-S3

**Pass date: 2026-08-22. Read-and-report.** No serial port was opened, nothing
was flashed, `firmware/` and `data/raw/` were not modified, nothing was staged
or committed.

Every claim below is graded **established** (re-derivable right now by a named
command against a named file), **permitted** (consistent with the files but
not shown by them), or **unknown**. Line numbers are from the files as they sit
in the working tree today.

---

## 0. The answer

**Both. Every telemetry byte is written to UART0 *and* to the native
USB-Serial-JTAG peripheral, in that order, in the same call.** The host's COM
port receives the stream from USB-Serial-JTAG. But the drain task is paced by
the UART0 write, which busy-waits on the TX FIFO at 460,800 baud — **46,080
B/s**, whether or not anything is connected to the UART pins.

So the framing of the question — "UART0 *or* native USB" — has no true answer.
The **transport that reaches the PC is native USB**. The **transport that sets
the rate is UART0**. The case for the S3 rested on those being the same thing,
and they are not.

**Settled at step 2**, by the console configuration plus the ESP-IDF v5.5.4
sources the build actually used. No hardware step is needed. Step 5 is not
reached; §6 records the confirmation run anyway, as a cheap check rather than
as the thing that decides it.

---

## 1. Step 1 — where the drain task writes

**Established.** It writes to `stdout`. There is no direct peripheral call
anywhere in the `csi_rx` output path.

`firmware/common/telemetry/telemetry.c:37-40`, inside `emit()`:

```c
    fwrite(hdr, 1, sizeof(hdr), stdout);
    fwrite(payload, 1, len, stdout);
    fwrite(&cks, 1, 1, stdout);
    fflush(stdout);
```

`emit()` is reached only from `tlm_send_csi` (`telemetry.c:43-61`) and
`tlm_send_status` (`:63-78`); the drain task calls the former at
`firmware/csi_rx/main/main.c:180-181`, and `main.c:163-164` states the
single-writer contract.

Re-derive:

```
grep -rn --exclude-dir=build -E "uart_write_bytes|usb_serial_jtag_write_bytes|fwrite|stdout" \
  firmware/common firmware/csi_rx/main
```

The only `uart_*` calls in the whole `csi_rx` build are in
`firmware/common/node_hal/node_hal.c:136-139,160,191` — all inside
`hal_diag_console()`, the safe-boot path, which runs with RF off and never
returns (`main.c:287-290`). No `usb_serial_jtag_*` call exists in `csi_rx` at
all. (`firmware/s3_throughput/main/main.c:175,193,267` does call it directly,
but that project shares nothing with `csi_rx` and, per its own README line 17,
has never run.)

Step 1 is therefore **not** decisive on its own, exactly as anticipated. It
hands the question to the console configuration.

---

## 2. Step 2 — console configuration for the esp32s3 build

### 2.1 The configured values

`firmware/csi_rx/sdkconfig` is gitignored; these are read from the working-tree
file. Target is `esp32s3` (`sdkconfig:391`, `CONFIG_IDF_TARGET="esp32s3"`).

| line | symbol | value |
|---|---|---|
| `:1295` | `CONFIG_ESP_CONSOLE_UART_DEFAULT` | **not set** |
| `:1296` | `CONFIG_ESP_CONSOLE_USB_CDC` | **not set** |
| `:1297` | `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG` | **not set** |
| `:1298` | `CONFIG_ESP_CONSOLE_UART_CUSTOM` | **=y** |
| `:1299` | `CONFIG_ESP_CONSOLE_NONE` | not set |
| `:1300` | `CONFIG_ESP_CONSOLE_SECONDARY_NONE` | **not set** |
| `:1301` | `CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG` | **=y** |
| `:1302` | `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG_ENABLED` | =y |
| `:1303` | `CONFIG_ESP_CONSOLE_UART` | =y |
| `:1304` | `CONFIG_ESP_CONSOLE_UART_CUSTOM_NUM_0` | =y |
| `:1306` | `CONFIG_ESP_CONSOLE_UART_NUM` | **0** |
| `:1307` | `CONFIG_ESP_CONSOLE_ROM_SERIAL_PORT_NUM` | 0 |
| `:1308` | `CONFIG_ESP_CONSOLE_UART_TX_GPIO` | **1** |
| `:1309` | `CONFIG_ESP_CONSOLE_UART_RX_GPIO` | **3** |
| `:1310` | `CONFIG_ESP_CONSOLE_UART_BAUDRATE` | **460800** |
| `:535` | `CONFIG_ESP_ROM_CONSOLE_OUTPUT_SECONDARY` | =y |
| `:1983` | `CONFIG_LIBC_STDOUT_LINE_ENDING_LF` | **=y** (no `\n`→`\r\n` expansion) |

**So the primary console is a custom UART — UART0, TX on GPIO1, 460,800 baud —
and USB-Serial-JTAG is the *secondary*.** The `sdkconfig.defaults`
(`firmware/csi_rx/sdkconfig.defaults:8-12`) says so in as many words: "Custom
UART console = same UART0/GPIO1/GPIO3 as Default, but unlocks the baud field".

**Established that this is what was built.** The generated header
`firmware/csi_rx/build/config/sdkconfig.h:606-615` carries the identical
values, `:890` carries `CONFIG_LIBC_STDOUT_LINE_ENDING_LF 1`, and
`build/project_description.json` records
`"idf_path": "C:/Espressif/frameworks/esp-idf-v5.5.4"`. mtimes: `sdkconfig`
and `build/config/sdkconfig.h` 2026-08-21 12:20, `build/csi_rx.bin` 12:22 —
28 minutes before the 12:50:17 capture.

**Still permitted, not established:** that `csi_rx.bin` is what was on the
board during either pinned session. mtime ordering is circumstantial, as
`docs/OLED_AND_MARGINAL_CELL.md` §4.3 already said. Nothing in this pass
improves on that.

Note that GPIO1/GPIO3 are the **ESP32** DevKit UART0 pins, not the S3's
defaults — `docs/S3_PORT_SCOPE.md:127-128` already flagged this as an ESP32-ism
carried into an S3 build. It does not change the answer (see §3).

### 2.2 The crux: does stdout go to the primary only, or to both?

**Established — to both.** The prior pass could not retrieve this
(`docs/OLED_AND_MARGINAL_CELL.md` §4.3(i): "an IDF-internal behaviour this pass
could not retrieve; `raw.githubusercontent.com` timed out"). The sources are on
disk. From the exact IDF the build used,
`C:\Espressif\frameworks\esp-idf-v5.5.4\components\esp_vfs_console\vfs_console.c:80-88`:

```c
ssize_t console_write(int fd, const void *data, size_t size)
{
    // All function calls are to primary, except from write and close, which will be forwarded to both primary and secondary.
    write(vfs_console.fd_primary, data, size);
#if CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG
    write(vfs_console.fd_secondary, data, size);
#endif
    return size;
}
```

The file's own header comment (`vfs_console.c:25-29`) states the design
intent: "which can help us to output some string to two different ports (i.e.
both through uart and usb_serial_jtag) … we set a port as primary and another
as secondary. For primary, it is used for all the features supported by each
vfs implementation, while the secondary is only used for output."

Espressif's Kconfig help text says the same, and is present in the build tree
without needing the IDF checkout —
`firmware/csi_rx/build/config/kconfig_menus.json`, symbol `ESP_CONSOLE_SECONDARY`:

> This secondary option supports output through other specific port like
> USB_SERIAL_JTAG when UART0 port as a primary is selected but not connected.
> This secondary output currently only supports non-blocking mode without using
> REPL.

and symbol `ESP_CONSOLE_UART`: "Select where to send console output (through
stdout and stderr)."

Independently corroborated by the linked image: `build/csi_rx.map` shows
`libesp_vfs_console.a(vfs_console.c.obj)` contributing **both**
`.bss.primary_vfs` and `.bss.secondary_vfs` (the latter compiles in only under
`CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG`), a single `.text.console_write`,
and both backends linked: `libesp_driver_uart.a(uart_vfs.c.obj)` and
`libesp_driver_usb_serial_jtag.a(usb_serial_jtag_vfs.c.obj)`.

Re-derive:

```
grep -o -E "lib(esp_vfs_console|esp_driver_uart|esp_driver_usb_serial_jtag)\.a\([a-z_0-9]+\.c\.obj\)" \
  firmware/csi_rx/build/csi_rx.map | sort -u
grep -B1 "libesp_vfs_console.a(vfs_console.c.obj)" firmware/csi_rx/build/csi_rx.map \
  | grep -o -E "\.(text|bss)\.[A-Za-z_0-9]+" | sort -u
```

### 2.3 The primary write blocks — this is the throttle

**Established.** `fd_primary` is UART0. The UART VFS write is
`C:\Espressif\frameworks\esp-idf-v5.5.4\components\esp_driver_uart\src\uart_vfs.c:226-249`,
which loops over the buffer calling `s_ctx[fd]->tx_func` **once per byte**. The
default `tx_func` is `uart_tx_char` (`uart_vfs.c:98`, in `VFS_CTX_DEFAULT_VAL`,
applied to UART0 at `:105-111`), and `uart_tx_char` is
(`uart_vfs.c:185-195`):

```c
static void uart_tx_char(int fd, int c)
{
    uart_dev_t* uart = s_ctx[fd]->uart;
    const uint8_t ch = (uint8_t) c;

    while (uart_ll_get_txfifo_len(uart) < 2) {
        ;
    }

    uart_ll_write_txfifo(uart, &ch, 1);
}
```

A **busy-wait spin** on TX-FIFO space. It is replaced only by
`uart_vfs_dev_use_driver()`, which `csi_rx` never calls — the only occurrences
of that symbol anywhere in `firmware/` are symbol-table entries inside
`csi_tx/build_s3/csi_tx.map`, not call sites:

```
grep -rn --exclude-dir=build -E "use_driver|use_nonblocking" firmware/
```

returns no source hit. (`node_hal.c:139` installs the UART *driver*, but that
is a different call, in the safe-boot path, and does not switch the VFS
`tx_func`.)

The secondary write, by contrast, is
`components/esp_driver_usb_serial_jtag/src/usb_serial_jtag_vfs.c:183-207` with
default `tx_func = usb_serial_jtag_tx_char_no_driver` (`:117`), which does not
spin on a baud rate.

**Conclusion, established:** every 284-byte frame costs the drain task a
busy-wait of 284 × 10 bits ÷ 460,800 = **6.163 ms** on the primary UART before
the USB write is even attempted. The ceiling is **46,080 B/s = 162.25 fps** at
284 B/frame.

---

## 3. Step 3 — the USB-UART bridge question

**What the repo supports.** The board is a Heltec HTIT-WB32LAF
(`docs/HANDOFF.md:33`), MAC `8c:fd:49:b7:b0:6c`. `esptool` reported
`USB mode: USB-Serial/JTAG` reaching it on COM6
(`firmware/s3_throughput/README.md:47-51`), and that README concludes at
`:69-72` that "COM6 *is* the S3's native USB". `docs/CODE_INVENTORY.md:105-106`
labels the two 2026-08-21 receivers "Heltec S3, native USB" and "D0WD, UART
bridge".

**What the repo does not support.** Nothing in this tree documents the Heltec
V3's schematic, its bridge chip or absence of one, or where GPIO1 and GPIO3
terminate on that board. I did not fetch a vendor page this pass. So:

- **Established:** the host talks to the S3 over the chip's own USB-Serial-JTAG
  peripheral, not over a bridge.
- **Unknown:** whether UART0 TX on GPIO1 reaches a header pin, an LED, the LoRa
  module, or nothing at all on the HTIT-WB32LAF.

**This is the part that makes step 3 not matter.** `uart_tx_char` waits on
`uart_ll_get_txfifo_len` — the TX FIFO of the UART peripheral. That FIFO drains
at the configured baud rate into the pin regardless of what, if anything, is on
the other end. **An unconnected UART throttles exactly as hard as a connected
one.** The prior pass's framing — "data arriving on the host COM port could not
have come from UART0, therefore the UART is not the ceiling" — is a valid
premise with an invalid conclusion. The data indeed did not come from UART0.
The rate still did.

---

## 4. Step 4 — reconciling 94.44 % and 94.38 %

The link **is** the UART budget, so no alternative explanation is needed for
the *magnitude* or for why two independent sessions land on the same number.
What remains is the ~5.6 % shortfall from 100 %.

Arithmetic (`python3`, 284 B/frame from `telemetry.c:21-41` and `:43-61`;
12 hdr + 15 + 256 + 1 XOR):

| file | fps | period | UART time | excess |
|---|---|---|---|---|
| `s3_20260821_125017` | 154.08 | 6.4901 ms | 6.1632 ms | **+0.3269 ms (5.04 %)** |
| `s3_20260822_023034` | 153.18 | 6.5283 ms | 6.1632 ms | **+0.3651 ms (5.59 %)** |
| `s3_20260822_144424` | 144.30 | 6.9300 ms | 6.1632 ms | +0.7668 ms (11.07 %) |
| `desk_20260821_125017` | 137.05 | 7.2966 ms | 6.1632 ms | +1.1334 ms (15.53 %) |
| `d0wd_20260822_023034` | 128.22 | 7.7991 ms | 6.1632 ms | +1.6359 ms (20.98 %) |
| `d0wd_20260822_144424` | 124.81 | 8.0122 ms | 6.1632 ms | +1.8490 ms (23.08 %) |

(fps figures quoted from `docs/OLED_AND_MARGINAL_CELL.md` §4.2, which cites
`report` R2; not re-measured here.)

So the S3's two pinned sessions are **0.33 ms and 0.37 ms per frame** above a
saturated 460,800-baud UART, and the D0WD is 1.1–1.8 ms above it.

**Candidates for the 0.33–0.37 ms, none of them measured:**

1. **The secondary USB write runs after the UART write, not concurrently**
   (`vfs_console.c:83` then `:85`). It is a per-byte loop with an FIFO-writable
   poll (`usb_serial_jtag_vfs.c:195-204`, `:152-170`), so 284 iterations of
   real work per frame.
2. **`emit()` issues three `fwrite`s plus an `fflush`** (`telemetry.c:37-40`),
   so the whole VFS chain — two recursive lock acquire/release pairs per write
   — runs three times per frame rather than once.
3. **Per-frame CPU in the drain task**: `update_motion()`
   (`main.c:137-161`, 64 `sqrtf` plus two 64-float `memcpy`s) and `cal_feed()`,
   both on the critical path at `main.c:177-178`.
4. **The 4 Hz `display_task`** blasting a 1 KB I²C framebuffer
   (`main.c:208-249`), which is V2_SPEC §7(a)2's other candidate — though
   `docs/OLED_AND_MARGINAL_CELL.md` establishes the OLED was absent on the
   boards that produced these files.

**Honest position: the 5.6 % is unexplained.** Candidate 1 is the one this pass
newly makes available and it is the one I would instrument first, but a
back-of-envelope for it is not in this document because I have no measurement
of the USB FIFO poll cost. Note also that under FIFO buffering a purely
serial-then-idle model predicts the UART would *not* starve at these duty
cycles, so the excess is not trivially "time spent away from the UART" either.
`docs/V2_SPEC.md` §2.7's `emit_ns_accum` ÷ `emit_count` is the right
instrument, and it now has a specific hypothesis to test.

The D0WD's 79–86 % needs no link explanation at all: it is not near the budget,
and on the overnight capture it lost 0.579 % of frames
(`docs/V2_SPEC.md` §5.4). Its `sdkconfig.old` (`:252` target `esp32`,
`:1117-1127`) is the same UART0-at-460800 console **with no secondary stanza at
all** — so the D0WD writes once, to a UART that goes to a bridge chip, and the
S3 writes twice.

---

## 5. Step 5 — not reached

Steps 1–3 are decisive; no hardware experiment is required to establish the
link path. §6 gives the confirmation run because it is nearly free, not because
the question is open.

---

## 6. The cheap confirmation, if he wants it anyway

`docs/OLED_AND_MARGINAL_CELL.md` §4.3 already specified it and it is still the
right check — it now has a **predicted result**, which is what makes it worth
running:

> In `firmware/csi_rx/sdkconfig`, set `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y` as
> the **primary** console (and `CONFIG_ESP_CONSOLE_SECONDARY_NONE=y`), rebuild,
> reflash the S3, re-capture.

- **Prediction if this document is right:** the 154 fps ceiling moves upward.
  The UART busy-wait is gone from the path entirely.
- **If the ceiling does not move**, this document is wrong about which of the
  two writes dominates, and §2.7's `emit_ns_accum` decides among the remaining
  candidates.

A second, weaker discriminator needing no reflash of the console: halve
`CONFIG_ESP_CONSOLE_UART_BAUDRATE` to 230400 and re-capture. If the fps ceiling
roughly halves, the UART is the pacer. This is the experiment the brief
proposed; it is now a confirmation rather than a decider.

**Before either:** `docs/S3_PORT_SCOPE.md:114-128` and `docs/V2_SPEC.md` §4.5
warn that `hal_diag_console()` hard-codes `UART_NUM_0`. Moving the primary
console to USB-Serial-JTAG leaves safe-boot talking to a UART nobody is
listening to. That is a known consequence, not a new one, but it should not be
discovered on the bench.

---

## 7. Conclusions from this week that need revisiting

The link **is** paced by UART, so all of these are live. Ordered by how much
they move.

### 7.1 "The S3 is on native USB, the D0WD is on a UART bridge" — as an explanation of anything

- **`docs/CODE_INVENTORY.md` §1.3**, table at `:105-106`: the receiver column
  reads "Heltec S3, native USB" against "D0WD, UART bridge". True about the
  *host* connector, misleading as an account of the difference between them.
  Both nodes write every byte into a 460,800-baud UART0; the S3 additionally
  writes each byte a second time to USB. **The S3 has more transport work per
  frame than the D0WD, not less.**
- Same section, `:117-118`: "The S3 in the reported test ran at ~6 % of its
  measured 675 KB/s link … so the USB link is not the constraint there." The
  675 KB/s figure has no artifact (`docs/S3_PORT_SCOPE.md` §0,
  `docs/V2_SPEC.md` §5.4) and the sentence's conclusion is right for the wrong
  reason: USB is not the constraint, but a link *is*.
- **`docs/CODE_INVENTORY.md` §1.3 "Unknown … why the drain task falls behind"**
  and **§6**, and **`docs/V2_SPEC.md` §7(a)2** ("Is the S3's 154 fps ceiling
  `emit()` or the OLED?"): the candidate list was two, then three after
  `docs/OLED_AND_MARGINAL_CELL.md` §4. **The third candidate is now the
  established mechanism** and (a)2's question needs restating as "what accounts
  for the residual 5 % above the UART budget?"

### 7.2 The zero-corrupt-rows asymmetry

- **`docs/V2_SPEC.md` §2.1** is already careful here: `:92-102` explicitly
  disowns the "USB CDC carries CRC16 and retransmission; UART carries nothing"
  premise as appearing in no file, and rests the case on the 142-against-0 and
  100-against-0 asymmetries with `docs/DUAL_RX_2026-08-21.md` §2.1's caveat
  that attributing it to the link "is an inference from the two files, not a
  measurement of either link". **That caution is now vindicated and should be
  hardened, not softened.** If any later text leans on transport CRC, it is
  leaning on a link the S3's bytes do travel — but the *inference* that the S3
  is corruption-free *because* it is on USB has to survive the fact that the
  S3's bytes also traverse a UART, and the D0WD's traverse a UART plus a bridge
  chip. The bridge, not the UART, is then the differing element.
- **A new mechanism this pass turned up, not previously in any file:** the
  secondary USB path **silently discards bytes**.
  `usb_serial_jtag_vfs.c:183-188` returns −1 without writing if
  `usb_serial_jtag_is_connected()` is false, and
  `usb_serial_jtag_tx_char_no_driver` (`:152-170`) drops every byte once
  `TX_FLUSH_TIMEOUT_US` (50 ms, `:78`) has elapsed since the last successful
  write. Dropped whole bytes produce **resync and frame loss, not CRC
  failures** — so "zero corrupt rows on the S3" is *compatible* with the S3
  losing frames in transport, and the two are not alternatives. This bears
  directly on §2.1 and on §7(b)4.
- **`docs/OCCUPANCY_TEST_0822.md` §2.1** ("15 corrupt rows on the d0wd, 0 on
  the S3") — the observation stands; only the causal story is affected.

### 7.3 The 14.906 % queue-drop attribution

- **`docs/OVERNIGHT_2026-08-22.md` §4.3** and **`docs/V2_SPEC.md` §2.2**
  (`:113-115`) and **§5.4**: 624,291 drops, 14.906 % loss, against a delivered
  rate pinned at 153.2–153.7 fps. §5.4 concludes "**The ceiling is in the drain
  path**". **That conclusion is now specific rather than open: the drain path's
  ceiling is `console_write`'s primary UART busy-wait, 6.163 ms of every
  6.53 ms frame period.** The queue drops are the consequence — offered 175–204
  fps (`docs/DUAL_RX_2026-08-21.md` §2.5) against a 162.25 fps hard ceiling
  overflows a 64-deep queue by construction.
- **`docs/CODE_INVENTORY.md` §1.3 item 3**, "it is not serial saturation" —
  that heading needs rewriting. It is serial saturation; it is just not
  saturation of the serial link the host is plugged into.
- **`docs/V2_SPEC.md` §7(a)2**'s 250 ms-periodicity test on the drop deltas is
  still worth running, but a null result now has a ready explanation rather
  than leaving the question open.
- **`docs/V2_SPEC.md` §7(a)3 / §2.6** (does tail-drop bias the survivors?) is
  **unaffected in importance and more urgent in character**: a deterministic
  rate ceiling produces a *structured*, not random, drop pattern. Frames are
  refused when the queue is full, which is periodic against a fixed drain
  period. That is a stronger prior for bias than "the node fell behind
  sometimes".

### 7.4 The throughput measurement's relevance

- **`firmware/s3_throughput/`** measures `usb_serial_jtag_write_bytes` directly
  (`main.c:175,193`) with the console moved to USB-Serial-JTAG
  (README `:21-23`). **It therefore measures a path `csi_rx` does not use.**
  Its number, whenever it is finally run, is an upper bound on a transport the
  CSI receiver reaches only as a *secondary* console write behind a blocking
  UART. It remains worth running — it bounds what V2 could have — but it
  cannot be read as "what the S3 can sustain today".
- **`docs/V2_SPEC.md` §7(a)5** ("What does the S3's USB link actually
  sustain?") should carry that caveat.
- **`docs/S3_PORT_SCOPE.md` §0** already refuses the 675 KB/s premise; nothing
  there needs weakening.

### 7.5 The V2 transport requirement

- **`docs/V2_SPEC.md` §5.4, "Bandwidth, as a project — out of scope because it
  is not the constraint."** The reasoning was: a link losing 15 % of a 53 KB/s
  offered load is not a link problem at any plausible USB rate. **The premise
  was right about USB and wrong about the link.** The constraint is a
  460,800-baud UART carrying 100 % of a 53 KB/s offered load with a 46 KB/s
  budget. Whether that makes bandwidth "a project" is a judgement call — the
  fix may be one Kconfig line, which is why §5.4's conclusion may survive — but
  **the stated reason for it not being the constraint no longer holds.**
- **`docs/V2_SPEC.md` §1 / §7(b)**, and any V2 argument of the form "the S3 is
  the better instrument because native USB gives headroom above the UART's
  46,080 B/s": **that headroom is not being used.** It is available — one
  Kconfig change away — but no capture in `data/raw/` was taken with it.
- **`docs/V2_SPEC.md` §4.5** ("Port the safe-boot console off `UART_NUM_0`")
  moves from Should to a **prerequisite** of taking the headroom, since the
  Kconfig change that frees the S3 is the same one that strands
  `hal_diag_console()`.
- **`docs/DIRECTION.md`** — per `CLAUDE.md`, describes nothing that is built and
  is not cited here as capability.

### 7.6 What does *not* need revisiting

- Everything in the **phase domain**: `pc/rff/dsp.py` figures, the twin
  investigation, the SFO estimator, the 99.7 %/95.7 % device-ID pair. A rate
  ceiling changes how many frames arrive, not what the arriving frames say.
  `docs/V2_SPEC.md` §7(b)3's question (is the 14.9 % loss unbiased with respect
  to the phase estimate?) is the one place the two meet, and it was already
  open.
- The **occupancy** pipeline (`pc/occ/`) — separate pipeline, per `CLAUDE.md`;
  not cross-cited here.
- **`docs/OLED_AND_MARGINAL_CELL.md` §4.1–4.2**: the byte arithmetic and the
  measured rates. Both stand; §4.3's three "permitted, not established" items
  are what this document closes — (i) and (ii) established, (iii) still open.

---

## 8. Grading summary

**Established (named file, re-derivable now):** `emit()` writes to `stdout`;
the primary console is UART0 at 460,800 baud with USB-Serial-JTAG as secondary;
`console_write` writes to both; the primary UART write busy-waits per byte on
the TX FIFO; `csi_rx` never installs the UART VFS driver; the resulting budget
is 46,080 B/s = 162.25 fps at 284 B/frame; the D0WD build has no secondary
console; the secondary USB path can silently discard bytes.

**Permitted, not established:** that `build/csi_rx.bin` (12:22) is what ran
during the 12:50:17 and 02:30:34 sessions — mtimes only, unchanged from
`docs/OLED_AND_MARGINAL_CELL.md` §4.3(iii); that candidate 1 in §4 is the
dominant part of the 5 % residual.

**Unknown:** the 5.6 % shortfall's actual composition; where GPIO1/GPIO3
terminate on the HTIT-WB32LAF; whether any byte was in fact dropped by the
`TX_FLUSH_TIMEOUT_US` path in any session.

**Sources outside the repo:** ESP-IDF v5.5.4 at
`C:\Espressif\frameworks\esp-idf-v5.5.4`, the same tree
`build/project_description.json` names as `idf_path` — read directly, not
fetched, not quoted from memory.
