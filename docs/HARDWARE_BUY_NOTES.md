# Hardware Buy Notes — WiFi CFO Fingerprinting

**Prices and project status checked 2026-08-15.** Prices move fast right now (see
the memory-price note at the bottom) — re-check before ordering.

---

## For whoever is buying — plain list

### BUY (any one of these)

| What to buy | Price | Where |
|---|---|---|
| **Raspberry Pi 5, 4 GB** | $110 | [PiShop](https://www.pishop.us/product/raspberry-pi-5-4gb/) or [CanaKit](https://www.canakit.com/raspberry-pi-5-4gb.html) |
| **Raspberry Pi 4 Model B, 4 GB** | $100 | [PiShop](https://www.pishop.us/product/raspberry-pi-4-model-b-4gb/) |
| **Raspberry Pi 3 Model B+** | $40 | [PiShop](https://www.pishop.us/product/raspberry-pi-3-model-b-plus/) |

All three work equally well for this project's radio requirement. The price
difference buys computer speed, not radio capability. **The Pi 5 4 GB is the
recommended pick** — it works, and it's also the machine he plans to use as the
host for the sensor array.

**If you buy a Pi 5, it also needs:**

- Official 27 W USB-C power supply, $12.95 — [PiShop](https://www.pishop.us/product/raspberry-pi-27w-usb-c-power-supply-black-us/). A phone charger will *not* work; it needs 5 V / 5 A.
- Official Pi 5 Active Cooler, $10.95 — [PiShop](https://www.pishop.us/product/raspberry-pi-active-cooler/)
- microSD card, 32 GB or larger, ~$20 — [PiShop](https://www.pishop.us/product/raspberry-pi-sd-card-64gb/)

Pi 4 uses a different (5 V / 3 A USB-C) supply, ~$8. Pi 3B+ uses micro-USB, not USB-C.

### DO NOT BUY

| Item | Why not |
|---|---|
| **Raspberry Pi 400** (the keyboard one) | Different WiFi chip (BCM43456). The software this project needs does not support it. |
| **Raspberry Pi Zero 2 W** | Different WiFi chip (BCM/SYN43436). Not supported. Also out of stock everywhere. |
| **Raspberry Pi 500 / 500+** | Same problem class as the 400 — not verified as supported. Don't. |
| **Any USB WiFi adapter / "monitor mode" dongle** | Gives packets, not the radio measurements this project needs. Money wasted. |
| **RTL-SDR, HackRF, or any radio dongle under $200** | None can do the job. See technical notes. |

---

## Technical reasoning

### 1. Which Pi models Nexmon CSI actually supports

CSI extraction on a Pi requires the Nexmon firmware patch, which is written per
Broadcom/Cypress chip. The chip is what matters, not the board name.

| Board | Wireless chip | Nexmon CSI? |
|---|---|---|
| Pi 3B+ | BCM43455c0 | **Yes** — user-confirmed working Jan 2026 on a current image ([discussion #395](https://github.com/seemoo-lab/nexmon_csi/discussions/395)) |
| Pi 4B | BCM43455c0 | **Yes** — maintainer-confirmed 2026-07-28, incl. Debian 13 Trixie, no changes needed |
| **Pi 5** | BCM43455c0 (same chip as Pi 4, faster SDIO link) | **Yes** — this is the headline change |
| Pi 400 | **BCM/SYN43456** | **No** — not in the supported chip table |
| Pi Zero 2 W | **BCM/SYN43436** | **No** — not in the supported chip table |
| Compute Module 4 | usually BCM43455c0 | Unclear — an Apr 2026 CM4 report of `nex_init_netlink: socket error` on the new flow got **zero replies** ([#395](https://github.com/seemoo-lab/nexmon_csi/discussions/395)) |

**Pi 5 verdict — the one that decides the purchase.** It works, but this is
recent. Until Dec 2025 the Pi 5 genuinely did not work, and there is a pile of
closed-as-unanswered issues saying so ([#388](https://github.com/seemoo-lab/nexmon_csi/issues/388), #364, #286, #331, #359). On
2025-12-01 the maintainer (jlinktu) published `Makefile.rpi` plus a tutorial,
tested on a Pi 5 running Raspberry Pi OS Lite 64-bit Trixie. The upstream
[README](https://raw.githubusercontent.com/seemoo-lab/nexmon_csi/master/README.md)
chip table now reads `bcm43455c0 / 7_45_189 / Raspberry Pi 3B+/4B/5`. The new
flow drops the patched `brcmfmac` driver entirely, which is what used to pin
you to specific kernels; kernel 6.12 is confirmed working.

Pi 5 gotchas the buyer doesn't need to know but he does:

- Pi 5 must be switched off the 16 KB-page kernel (`kernel=kernel8.img` in
  `/boot/firmware/config.txt`) or the nexmon build fails.
- On any 64-bit image, the armhf multiarch step (step 3 of the tutorial) is
  **required**, not Pi-5-only — a Pi 3B+ user hit exactly this and it was the fix.
- `nexutil` must be built with `USE_VENDOR_CMD=1` or the driver rejects the
  ioctls silently. Also needs `setcap cap_net_admin+ep`.
- The build still needs Python 2.7 pulled from `archive.debian.org` stretch.

### 2. Is the project maintained?

Yes, actively — with a large unresolved backlog.

- Maintainer replied to questions on 2026-07-28, ~3 weeks ago.
- README updated to list the Pi 5; `Makefile.rpi` added Dec 2025.
- Builds against current kernels (6.12 confirmed by the maintainer) and Debian 13 Trixie.
- **But: 171 open issues.** Long-standing unfixed ones include
  [#39](https://github.com/seemoo-lab/nexmon_csi/issues/39) (open since 2020, `nexutil -k` reads back a wrong chanspec) and
  [#198](https://github.com/seemoo-lab/nexmon_csi/issues/198) (Pi 3B+ chip falls over after ~a minute of idling, closed
  as not-planned; the reporter gave up on the project).
- *Unconfirmed:* the exact last-commit date. GitHub's commit listing and the
  API returned empty bodies to every fetch attempt. Maintainer activity above is
  from dated comments, which is solid; the literal HEAD date is not verified.

### 3. Channel hopping — the weak spot for drive-by capture

This is where the honest answer is worse than the marketing.

**Mechanically it hops fine.** Two paths, both confirmed by reading the source:
`nexutil -k<chan>/<bw>` retunes only and leaves the extractor config alone
(filters live in firmware shared memory and survive), or re-running
`nexutil -s500 -b -l34 -v<params>` retunes *and* re-asserts scan-suppress and
MPC-off. No firmware reload needed. Every CSI UDP packet carries the chanspec
it was captured on, so packets can be labelled with their channel after the fact
rather than by timing.

**But two things bite:**

1. **Channels must be compiled in.** `src/regulations.c :
   additional_valid_chanspecs[]` is a hardcoded whitelist installed as a
   flashpatch on the validator, so it gates *both* the `-k` path and the ioctl
   path. Out of the box the 2.4 GHz entries are only channels 6, 7, 9, 13. A
   sweep across 1–13 means editing that array and rebuilding the firmware. Not
   hard, but it is a rebuild, not a runtime setting.
2. **Nobody has published a retune time.** *Unconfirmed, and this matters for
   the drive-by use case:* no measured settle time in milliseconds exists in the
   repo, issues, discussions, the WiNTECH'19 paper, or any blog post. The only
   number of any kind anywhere is an anecdote on a *different chip* (bcm4339,
   Nexus 5) saying 1 Hz hopping is smooth and 2 Hz got choppy — and that issue
   got zero replies. There is also no official hopping script; `nexmonster/picsi`
   has a "loop over profiles" feature that is an unchecked box on its own
   roadmap, and the repo says "not ready for testing yet."

Practical read: plan on hopping being roughly 1 Hz-class until measured, and
budget a bench session to measure it. For a transient drive-by, that means
choosing a channel and camping rather than sweeping — which is not obviously
better than the current fixed-channel-6 ESP32 setup.

### 4. Alternatives

**More ESP32s.** Cheapest capability per dollar by a wide margin, and it reuses
the entire existing pipeline. ESP32-S3-DevKitC-1-N8 is
[$15.95 at Adafruit](https://www.adafruit.com/product/5312) (81 in stock) or
[$15.00 via Mouser](https://octopart.com/search?q=ESP32-S3-DevKitC-1); official
plain ESP32-DevKitC-32E is [$10.00 at DigiKey](https://octopart.com/part/espressif-systems/ESP32-DEVKITC-32E).
*Note:* Octopart shows a **+319% three-month price trend** on the
ESP32-DEVKITC-32E, so this is not the stable $6 board it used to be.
*Unconfirmed:* Amazon multipack per-unit prices — Amazon blocked every fetch.
Also relevant to open thread #6: a **non-Espressif-D0WD** board is what breaks
the clock-twin problem, so buy a *different* module, not a fourth identical one.

**Pi + external USB adapter.** **This does not give CSI.** Nexmon patches the
firmware of the Pi's *internal* Broadcom chip; a USB dongle is a different
chipset running its own firmware and is completely outside Nexmon's reach. The
Atheros CSI Tool route doesn't rescue it either — its own issue tracker documents
that CSI collection returns nothing once the receiver is in monitor mode
([Atheros-CSI-Tool #11](https://github.com/xieyaxiongfly/Atheros-CSI-Tool/issues/11)).
An external adapter is only useful for keeping the Pi on the network while the
internal chip does CSI, and even for that the upstream advice
([#42](https://github.com/seemoo-lab/nexmon_csi/issues/42)) is to just use an
Ethernet cable.

**SDR under $200.** No. The blocker isn't bandwidth, it's frequency coverage —
the cheap ones can't see 2.4 GHz at all:

| SDR | Max instantaneous BW | Reaches 2.4 GHz? | Price |
|---|---|---|---|
| [RTL-SDR Blog V4](https://www.rtl-sdr.com/product/rtl-sdr-blog-v4-r828d-rtl2832u-1ppm-tcxo-sma-software-defined-radio-dongle-only/) | ~2.4 MHz | **No** — tops out at 1.766 GHz | $44.95 (out of stock) |
| [Airspy Mini](https://itead.cc/product/airspy-mini/) | ~6 MHz usable | **No** — 24–1700 MHz | $99 |
| [Airspy R2](https://itead.cc/product/airspy/) | ~9 MHz alias-free | **No** — 24 MHz–1.8 GHz | $169 |
| [HackRF One](https://greatscottgadgets.com/hackrf/one/) | 20 MHz (8-bit) | Yes | $339.95 (out of stock) |
| [ADALM-PLUTO](https://shop.richardsonrfpd.com/Products/Product/ADALM-PLUTO) | "up to 20 MHz" | Yes, 325 MHz–3.8 GHz | $243.73 |
| [LimeSDR Mini 2.0](https://www.crowdsupply.com/lime-micro/limesdr-mini-2) | 40 MHz | Yes | $600 |
| [bladeRF 2.0 xA4](https://www.nuand.com/product/bladerf-xa4/) | ~56 MHz | Yes | $540 |

The hunch in the brief was right, but for the wrong reason: RTL-SDR's bandwidth
*is* far too narrow, but it wouldn't matter — it can't tune to 2.4 GHz. Cheapest
thing that does both is the PlutoSDR at ~$244, exactly at its 20 MHz rating with
zero margin. Comfortable margin starts around $540–600.

---

## Bottom line

Buy the Pi 5 4 GB (or the Pi 3B+ if the budget is tight — the radio capability is
identical). The Pi 5 concern in the brief was correct as of a year ago and is
no longer correct as of Dec 2025.

The real risk isn't the board, it's the software: 171 open issues, a Python-2.7
build dependency, and a completely undocumented hop latency. Before committing
the CFO pipeline to it, bench-measure the retune gap and confirm the chip stays
up for a multi-hour capture — issue #198 says a Pi 3B+ didn't.

### Flagged unconfirmed

- Literal last-commit date on `seemoo-lab/nexmon_csi` (GitHub commit listing and
  API both returned empty; maintainer activity dated 2026-07-28 is confirmed).
- Nexmon CSI channel retune / settle time in ms — **no published measurement exists anywhere.**
- Maximum practical hop rate — no published measurement.
- Compute Module 4 status on the new `Makefile.rpi` flow.
- Whether Pi 500 / 500+ use a supported chip — not researched; assume not.
- Amazon ESP32 multipack per-unit prices (fetches blocked).
- Whether the BCM43455 firmware's own CFO correction leaves usable residual CFO
  for fingerprinting the way the ESP32 path does — **not researched.** Worth
  checking before assuming the Pi improves on the current 77% same-model result.
- `https://github.com/seemoo-lab/nexmon_csi` (repo root) — fetch was not approved;
  all repo facts above come from the raw README, the Makefile blob, issues, and
  discussion #395.

### Price context

Raspberry Pi raised prices on 2025-12-01 citing LPDDR4 costs
([announcement](https://www.raspberrypi.com/news/1gb-raspberry-pi-5-now-available-at-45-and-memory-driven-price-rises/)),
and street prices are running **~1.6–2x above MSRP**. The Pi 3B+ was explicitly
exempted from the increase, which is why a $40 3B+ against a $110 Pi 5 4 GB is a
much wider gap than it used to be. Pi 4B remains in production to at least Jan
2034, Pi 3B+ to at least Jan 2030.
