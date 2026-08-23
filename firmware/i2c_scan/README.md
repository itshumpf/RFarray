# i2c_scan

One question, one answer: **which GPIOs is the OLED actually on, on the
Heltec WiFi LoRa 32 V3 (`8c:fd:49:b7:b0:6c`)?**

`docs/S3_PORT_SCOPE.md:132-137` already flagged that `csi_rx`'s
`OLED_SDA 21` / `OLED_SCL 22` are DevKit-convention pins and that **"the
Heltec's own I²C OLED wiring is not recorded anywhere in this repo."**
This app is that missing measurement.

The published pinouts disagree — Heltec's Arduino core says SDA 8 / SCL 9,
community threads say other things, and Heltec's own repo carries an open
issue titled *"LoRa 32 V3: OLED\_SDA / OLED\_SCL Pin Locations"*. None of
those is evidence about **this** board, so this app asks the board.

Note what is *not* known going in. `csi_rx` **would** log `OLED not found
on SDA=21 SCL=22 — running headless`, but that line goes to stdout, into
the binary telemetry stream, where `pc/rff/protocol.py`'s resync throws it
away as non-frame bytes. It reaches no file in `data/raw/` and **nobody has
ever read it** (`docs/OLED_AND_MARGINAL_CELL.md` §2.4). That section also
lists what stays open: whether `oled_init` failed at `i2c_new_master_bus`,
at the device add, or at the first command byte, and whether a panel is
wired to 21/22 at all. This app settles the pin question head-on and does
not depend on that log line existing.

It scans; it does not assume. It never initialises an SSD1306, never draws
anything, and never writes to the panel — a bare address ACK is the whole
result.

Nothing in this directory is shared with `csi_rx` / `csi_cfo` / `csi_tx`.
It deliberately does not use `../common` (no `node_hal`, so no `ssd1306.c`
and none of its hard-coded pins), and has no WiFi, no BLE, no LoRa, no
NVS, no PSRAM. **No file outside `firmware/i2c_scan/` was touched.**

## State: written, NOT built, NOT flashed, NEVER run

Written without ESP-IDF available, so unlike `s3_throughput` this has
**not been compiled even once**. Nothing below has been observed; the
output shapes are what the code prints, read off the source. The first
`idf.py build` is the first real test of it. In particular
`i2c_master_probe()` and the `esp_driver_i2c` / `esp_driver_gpio`
component names in `main/CMakeLists.txt` are from the IDF 5.x
`i2c_master` API as used in `common/node_hal/ssd1306.c` — believed right
for v5.5.4, unverified here.

## What it does

Three unknowns are separated instead of confounded:

1. **Power first.** GPIO36 is reported as the Vext control on the V3, and
   Vext is a *switched* 3.3 V rail — with it off the panel is unpowered
   and every probe fails no matter how right the pins are. The polarity is
   **not settled**, so all three states are tested: driven low, driven
   high, and left floating as an input, with a 300 ms settle after each
   change. The report says which one produced ACKs, or that none did.
2. **Pins.** Every ordered pair drawn from 25 swept GPIOs, so a pinout
   documented backwards still gets found. The eight specifically published
   pairs — (17,18), (21,22), (8,9), (4,15) and all four reversals — are
   *also* probed verbosely first, so each published claim gets its own
   attributable yes/no line.
3. **Reset.** These panels commonly need a reset line released before they
   answer. Scanned with no reset, then with GPIO16 pulsed low-high, then
   with GPIO21 pulsed. The report says whether reset changed the outcome.

3 rail states x 3 reset options = 9 independent sweeps. **Both** SSD1306
addresses `0x3C` and `0x3D` are probed at every pair, and **every** address
that answers is printed — if some third-party part is on that bus, that is
worth knowing and is not filtered out.

A pair whose SDA or SCL reads low under a pullup is skipped before any
transaction (an idle I2C bus rests high on both lines), and the offending
GPIO is named. That keeps the run to roughly a minute instead of stalling
on every held line.

### Pins deliberately not swept

| GPIO | why not |
|---|---|
| 0, 3, 45, 46 | ESP32-S3 strapping — boot mode, JTAG source, VDD\_SPI, ROM log. Driving them is how you get a board that will not boot. |
| 19, 20 | USB D−/D+ — the console this report is printed on. |
| 22–25 | Do not exist on the ESP32-S3. |
| 26–32 | SPI flash (CS0/CLK/Q/D/HD/WP/CS1). Driving = crash. |
| 33–35, 37 | Octal-PSRAM lines on `-R8` parts. |
| 36 | Held as Vext for the whole run, so it is never also a bus pin. |
| 43, 44 | UART0 TX/RX, where the ROM and bootloader log. |

Swept: 1, 2, 4–18, 21, 38–42, 47, 48. Those are driven **open-drain** by
the I2C peripheral, so the worst this does to a neighbour (the SX1262 sits
on several of these on a V3) is pull one of its lines low briefly, or
reset it. Nothing is held, and nothing is driven high.

**`(21,22)` cannot succeed on this chip** — GPIO22 does not exist on the
ESP32-S3, so `gpio_config` rejects it. That is `csi_rx`'s current
`OLED_SDA`/`OLED_SCL`: an ESP32-classic pinout on an S3. The app probes it
anyway so the failure appears in the log as a measurement rather than as
something I inferred for you.

## Build and flash

> ### ⚠ This replaces `csi_rx` on the board
>
> There is one application partition. Flashing `i2c_scan` **overwrites the
> running receiver** — the S3 stops capturing CSI the moment this lands,
> and stays stopped until you flash `csi_rx` back. Both commands are
> below; do not walk away between them.

```powershell
# IDF env (docs/HANDOFF.md, "Hard-won gotchas")
$env:IDF_TOOLS_PATH = "C:\Espressif"
$env:IDF_PYTHON_ENV_PATH = "C:\Espressif\python_env\idf5.5_py3.11_env"
. C:\Espressif\frameworks\esp-idf-v5.5.4\export.ps1

cd C:\dev\csi-array\firmware\i2c_scan
idf.py set-target esp32s3               # only needed once
idf.py build
idf.py -p COM6 --no-stub -b 115200 flash monitor
```

**Then put the receiver back:**

```powershell
cd C:\dev\csi-array\firmware\csi_rx
idf.py -p COM6 --no-stub -b 115200 flash
```

**Do not `fullclean` or delete `firmware/csi_rx/sdkconfig` when you do
that.** That file (mtime 2026-08-22) has the console on
`CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y`, but `csi_rx/sdkconfig.defaults`
still asks for the custom UART console at 460800 and was never updated to
match. Regenerating `sdkconfig` would silently move `csi_rx`'s output back
to UART0. `sdkconfig` is gitignored, so there is no copy in the repo to
restore from — `sdkconfig.uart-backup` next to it is the *old* UART
config, not a spare of the current one.

`--no-stub -b 115200` is not optional and not superstition: the esptool
stub dies over ROM USB-CDC on this board and the 460800 rebaud is flaky
(`docs/HANDOFF.md`, "Hard-won gotchas"; reproduced on 2026-08-21 in
`firmware/s3_throughput/README.md`). If it still refuses, hold BOOT and
tap RST for manual download mode. Pull the LiPo while debugging — USB
unplug does not reboot a Heltec and uptimes lie. A manual RST may be
needed after flash.

**COM6** is where `docs/S3_LINK_PATH.md:228` records esptool reaching this
board in USB-Serial/JTAG mode. Confirm it is still COM6 before flashing;
Arduino IDE steals ports.

## Reading the output

**`idf.py monitor` works on this app.** Its stdout is plain ASCII text.
That is not true of `csi_rx`, whose stdout is a binary v2 telemetry frame
stream that a terminal will render as garbage — for `csi_rx` you use
`pc/capture.py`, never `monitor`.

The run opens with the board's own MAC, so you can tell at a glance
whether you are looking at `8c:fd:49:b7:b0:6c` or at the sibling board.
Then nine sweep blocks, then a verdict. A hit prints as it happens:

```
--- Vext GPIO36 driven LOW ---

  reset: none
    documented pairs:
    SDA=17 SCL=18  Heltec V3 board files / community threads
      *** ACK  SDA=17 SCL=18 addr=0x3C
    ...
    full sweep: 583 pairs probed, 17 skipped (line not idle), 1 ACK
```

and the verdict names one configuration outright:

```
================ RESULT ================
FOUND. 6 ACKs across all combinations.

  Vext (GPIO36) : driven LOW
  SDA           : GPIO17
  SCL           : GPIO18
  reset pin     : none needed
  address       : 0x3C
```

followed by whether the rail state mattered, whether reset mattered, and
every ACK unfiltered.

If nothing answers anywhere, it says so plainly and lists exactly what was
tried — rail states, reset options, addresses, the named pairs, the swept
pin list, and how many pairs were probed vs skipped. **That is a real
result**, and it points at an absent or dead panel rather than at a
mis-documented pinout.

## What it would take to act on the answer

Nothing here changes `csi_rx`. If the scan finds the panel, the change is
`OLED_SDA` / `OLED_SCL` at `firmware/csi_rx/main/main.c:62-63` — and, if
the run reports that a reset pulse was required, a pulse and a Vext
assertion before `oled_init()`, neither of which `ssd1306.c` currently
does. That is a separate edit to a working receiver, and is not made here.

## Things to verify on the first real run

1. **That it compiles.** Never built. See "State" above.
2. **That GPIO36 is safe to drive on this package.** esptool reported
   `Embedded PSRAM 2MB` for this board, i.e. *quad* PSRAM sharing the
   flash bus, which leaves GPIO33–37 idle — and `CONFIG_SPIRAM` is off
   anyway. On an octal (`-R8`) part GPIO36 is a PSRAM data line and
   driving it would crash the moment `vext_apply()` runs. If the board
   resets immediately at the first `--- Vext GPIO36 ---` banner, that
   assumption was wrong: stop, and re-check the module marking.
3. **That GPIO36 is the Vext control at all.** That is the one pin whose
   role this app takes on trust, from Heltec's documentation rather than
   from measurement. If all three rail states behave identically, it
   probably is not gating this panel — the verdict says so explicitly.
4. **The reset candidates are guesses.** GPIO16 and GPIO21 are the two
   commonly cited for `RST_OLED` on this board; neither is confirmed here.
   If GPIO21 turns out to be a *bus* pin, the reset pass that pulses it
   excludes it from that sweep — the verdict's "yes, backwards" branch is
   what that looks like.
5. **Sweep duration.** Roughly a minute is an estimate from 9 sweeps x
   ~600 pairs x 2 addresses, not a measurement. If a lot of lines are held
   low it will be much faster; if `i2c_master_probe` is slower than
   assumed on a NACK, much slower.
6. **Bus pullups are the ESP32's internal ones** (`enable_internal_pullup`,
   the same as `ssd1306.c`), which are weak. If the panel has no external
   pullups and long traces, a marginal ACK is possible — but the Heltec
   OLED is on-board, so this is unlikely to bite.
