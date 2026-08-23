# PROJECT_NOTES.md — verification pass, 2026-08-02

Read-only audit of what this repo actually supports, run against the code and
data as they sit on `main` right now (plus uncommitted working-tree changes —
see "Uncommitted state" below). Every number below either traces to a file I
read or a command I ran myself this session; anything I couldn't pin down
says so.

---

## 1. What's actually here

```
firmware/
  common/
    node_hal/       identity (NVS), crash counter, safe-boot diag console,
                     task + RF-liveness watchdogs, SSD1306 OLED driver
    telemetry/      binary protocol v1/v2 encoder (CSI + STATUS frames)
    calibration/    startup noise-floor baseline (dual-rate EMA)
  csi_tx/           beacon firmware (ESP32) — broadcasts 100 Hz ESP-NOW packets
  csi_rx/           promiscuous receiver firmware (ESP32) — CSI capture + OLED
  csi_cfo/          "clean-capture" receiver — see finding below: currently
                     byte-identical to csi_rx
  */build*/         ESP-IDF build output, gitignored, not hand-written

pc/
  rff/              device-ID pipeline: phase unwrap, RANSAC (dsp.py),
                     1D Kalman drift (kalman.py), reference-beacon
                     subtraction (reference.py), Mahalanobis/chi2
                     discriminator (discriminator.py), SQLite store (store.py)
  occ/              occupancy pipeline: motion z-score detector (motion.py),
                     respiration Welch-PSD scan (breathing.py), cross-link
                     zone clustering (zones.py) — entirely separate from rff/,
                     operates on amplitude not phase
  rff_offline.py     offline science run: per-source stats, pairwise sigma
                     separation, chronological train/holdout scoring
  occ_offline.py     offline occupancy run: motion timeline, respiration
                     scan, zone profiles, label-scored detection rates
  capture.py / collect.py / occ_capture.py   serial → CSV recorders
  field_diag.py, mac_census.py, device_correlate.py, zone_calib.py,
  fingerprint.py, phase_skew.py, heatmap.py, live_view.py   supporting tools
  test_occ_synth.py  synthetic DSP sanity checks (no dataset needed)

data/
  raw/              session CSVs — ~15M rows / ~13 GB across 62 files.
                     GITIGNORED — not in git, so cloning the repo does not
                     get you the dataset behind any published number.
  cache/            .npz caches of ingested amplitude grids (gitignored)
  fingerprints/     13 small JSON files, Phase-1 amplitude fingerprints
                     (tracked in git — the only data/ that is)
  rff.db            SQLite observation/model history (gitignored)

docs/
  HANDOFF.md              session-to-session engineering log (committed)
  OCC_PROTOCOL.md          scripted ground-truth capture protocol (committed)
  PROMPT_NEXT_SESSION.md   an AI-agent chat-start prompt, not documentation
                           (UNCOMMITTED)
  csi-array-case-study.md  the polished public narrative — source of the
                           headline claims (UNCOMMITTED)

site/                portfolio HTML (index.html = case study page,
                     resume.html) reusing the same headline numbers
                     (UNCOMMITTED, entire directory)

README.md            337 lines, accreted from v1 (raw capture) through v2
                     (RFF discrimination) through Phase 3 (occupancy) and
                     firmware v2 (field hardening) with no restructuring
```

No test suite beyond `pc/test_occ_synth.py` (synthetic, no real data needed).
No CI config found. No LICENSE file.

---

## 2. Claim-by-claim verification

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | ~15K lines of C/ESP-IDF firmware | **CONTRADICTED** | `wc -l` over every `.c`/`.h` outside `build*/`: **1,471 lines** (1,538 incl. CMakeLists/sdkconfig.defaults). No vendored/managed components exist to explain the gap. Off by ~10x. |
| 2 | 99.6% blind-holdout accuracy, 2.8M-frame dataset | **PARTIALLY SUPPORTED** | Dataset is real (`data/raw/`, ~15M rows / 13GB, gitignored). Split is genuinely **chronological** (`rff_offline.py:38,145-146` — first 60% of each source's windows train, last 40% test, files replayed in sorted/chronological order), not random. I reran the pipeline twice: desk-only 2026-07-13 files → **99.7% over 7,497 windows**; desk+node3 combined → **95.7% over 14,234 windows**. Neither run simultaneously reproduces "99.6% AND ~10,000 windows" as one pinned figure — the true number is sensitive to exactly which session files get included, and adding the second receiver *lowers* accuracy, not raises it. Order of magnitude (very high, dominated by the reference beacon's own huge, easy-to-classify sample count) is real. |
| 3 | 11–15σ cross-manufacturer separation, 7/7 holdout | **SUPPORTED (minor deviation)** | Reran full 2026-07-13 dataset (desk+node3): ambient device `1e:ce:51:f3:0d:fa` (locally-administered/randomized MAC, i.e. a real non-ESP32 device) separated at **12.7σ from the reference beacon and 10.4σ from the other ambient device**, with **6/6** blind holdout correct. Close to but not exactly 11–15σ / 7/7 — plausibly explained by pipeline refinements or file-set differences since the original measurement. The qualitative claim (decisive double-digit-sigma separation, near-perfect holdout for real ambient hardware) holds up. |
| 4 | Same-model ESP32 discrimination ≈77%, 1.8–2.7σ | **UNVERIFIED THIS SESSION** | Number is internally consistent across three docs (`README.md:194-196`, `docs/HANDOFF.md:38-40`, `docs/PROMPT_NEXT_SESSION.md:60-64`) but I did not run the `--only-macs` isolation of the two same-model beacons myself to confirm it. |
| 5 | Reference-beacon drift correction "doubled" separation | **PARTIALLY SUPPORTED** | Implementation is real and precisely as described: `pc/rff/reference.py` Kalman-smooths the known reference beacon's own (CFO,SFO) track, then subtracts that smoothed estimate from every other source's raw measurement at observation time — a common-mode/differential calibration against a known, always-on reference. Not literature-exotic; it's a standard differencing technique applied correctly to this hardware, so "novel" is a stretch but the engineering reasoning is sound. The specific "1.0σ → 2.6σ, more than doubled" figure appears identically in two docs but **no artifact in the repo (log, saved output, DB record) reproduces the "raw, uncorrected" baseline** — I did not have time to run that comparison myself. |
| 6 | Device ID and motion/respiration are separate pipelines | **SUPPORTED** | Confirmed by code: `pc/rff/` (phase-domain: RANSAC → Kalman → Mahalanobis/χ²) and `pc/occ/` (amplitude-domain: windowed z-score dispersion for motion, Welch-PSD SNR for respiration) share no discrimination logic. **The 99.6%/95.7%/11-15σ family of numbers is exclusively device-identification accuracy. It has no connection to motion or through-wall detection and must not be cited as such** — the "AI tools conflated it" error the task description mentions is a real, checkable mistake to correct. |
| 7 | Misc. other published claims | see below | |

### Other findings (item 7)

- **`firmware/csi_cfo/main/main.c` is byte-for-byte identical to `firmware/csi_rx/main/main.c`** (`diff` = no output; only the CMakeLists project name differs, and the `TAG` string inside `csi_cfo`'s own file still reads `"csi_rx"`). The README/case-study describe `csi_cfo` as a distinct firmware that "ignores ambient traffic and locks only onto the beacon" — as currently committed it runs identical promiscuous-mode code with the MAC filter disabled (`TX_FILTER_MAC` all-zero). **This description does not match the current code.**
- **Respiration range "7–12 bpm, 10–14 dB SNR" is narrower than the actual data.** I reran `occ_offline.py` on the exact cited session (`rx_20260715_201703.csv`, calibrated on `rx_20260714_030915.csv`) and pulled the full set of `PRESENCE`-verdict scans, not just the top-8 the CLI prints by default: **7.0–16.0 bpm (median 8.5), 6.1–15.2 dB SNR (median 9.2)**. The published range appears to quote only the strongest handful of detections.
- **The occupancy numbers rest on assumed labels**, not the scripted ground-truth protocol. `docs/HANDOFF.md` is explicit about this ("overnight = assumed no occupant," "scripted labeled session still pending"); the case study's phrasing ("recorded sessions... cleanly separated") doesn't carry that caveat forward. A scripted session **was** actually captured on 2026-07-22 (`data/raw/occ_20260722_*.csv`, 6 files) — five days after the last commit — but I found no evidence it was ever scored or the results written up anywhere.
- **Guard-bin claim checked directly against raw bytes**: sampled 5,000 frames, guard bins (|k| = 27–32, excluding DC which is separately and correctly described as dropped) were exactly zero in 4,994/5,000 (99.88%). **Supported.**
- **~4,000 lines of Python**: actual total is 4,573, but 614 lines come from three scripts (`device_correlate.py`, `mac_census.py`, `zone_calib.py`) that are new and **not yet committed**. Net of those, 3,959 — the claim matches the code as it stood when written. **Supported, just stale.**
- **The dataset behind every quantitative claim is not in the repo.** `data/raw/`, `*.csv`, and `data/rff.db` are all gitignored. A technical reviewer cloning this repo can read the pipeline but cannot rerun it against real data to check any number themselves.
- **What's publicly "claimed" is ahead of what's committed.** `docs/csi-array-case-study.md`, all of `site/`, and three `pc/` scripts are untracked; `firmware/csi_tx/main/main.c` has uncommitted changes on top. `git log` stops 2026-07-17; the case-study doc, the site, and the 07-22 occupancy captures all postdate the last commit.

---

## 3. What's proven vs. open (for Braeden's own use)

**Solid, reproducible, safe to state publicly as-is:**
- The physics model and DSP pipeline are real, sensibly designed, and match their code exactly (subcarrier mapping, RANSAC, Kalman, Mahalanobis/χ²).
- The holdout methodology is genuinely chronological — this is a real, non-trivial thing to have gotten right and is worth keeping in any public writeup.
- Device-ID and occupancy are genuinely separate, independently-validated pipelines.
- Firmware autonomy features (watchdogs, crash counter, calibration, telemetry v2) are real and match the code exactly.

**Needs a number correction before it's said again:**
- "~15K lines of firmware" → actual is ~1,500 lines. This is the single most overstated claim in the whole set and the easiest to just fix.
- "99.6% over 2.8M frames / ~10,000 windows" → defensible as "very high accuracy, low-to-mid 90s to high 90s depending on exact session selection," but the specific triplet of numbers doesn't reproduce as one pinned run. Worth either re-running and quoting the exact command + output, or loosening the claim to a range.

**Solid enough to keep, with the sigma value softened slightly:**
- Cross-manufacturer separation: real, large, double-digit sigma, near-perfect holdout. Reproduced at 10.4–12.7σ vs. published 11–15σ — close enough that "double-digit sigma separation" is a safe, defensible headline phrase even if the exact bound moves.

**Needs an explicit caveat added:**
- "Reference-beacon correction doubled separation" — the technique is real and correctly reasoned; the specific 2x/1.0σ→2.6σ figure has no reproducible artifact backing it that I could find. Either re-derive it and save the output, or say "materially improved" instead of a precise multiplier.
- Occupancy respiration range — either quote the true full range (7–16 bpm, 6–15 dB) or explicitly label the published range as "the strongest detections" rather than "the result."
- Occupancy detection generally — flag it as based on assumed, not scripted-ground-truth, labels until `occ_20260722_*.csv` gets scored.

**Needs fixing in the code/docs, not just the numbers:**
- `csi_cfo` is not currently a distinct clean-capture firmware — either implement the described behavior (promiscuous off, hard MAC filter on) or stop describing it that way.

---

## 4. Repo structure — an honest read

A stranger arriving at this repo on GitHub today would land on `README.md`
first (GitHub's default), which is a 337-line document that accreted through
four different phases of the project (raw capture → RFF v2 → occupancy →
field-hardened firmware) without ever being restructured. It reads like an
engineering log kept in the README, not an entry point. The actual polished,
non-technical-friendly narrative — `docs/csi-array-case-study.md` — is *not
even committed to git* and isn't linked from the README at all, so the best
version of the story is currently the hardest one to find.

Specific problems, roughly in order of how much they'd confuse a visitor:

1. **Four docs, no hierarchy, no cross-links.** `README.md`, `docs/HANDOFF.md`,
   `docs/PROMPT_NEXT_SESSION.md`, and `docs/csi-array-case-study.md` all
   describe overlapping parts of the same system from different angles, and
   none references the others. A visitor has no way to know which one is
   "the" documentation.
2. **`docs/PROMPT_NEXT_SESSION.md` isn't documentation — it's an AI-agent
   chat-start prompt**, written in second person to a future Claude session.
   Publishing it as-is reads strangely to a human visitor, and it currently
   contains household details (family members, pets, sleep schedules) that
   probably shouldn't be in a public repo at all.
3. **`site/` — a personal résumé/portfolio page — lives inside the
   engineering repo.** It's a different audience and a different concern
   from the firmware/DSP project, isn't linked from anywhere (its own
   `GITHUB_URL` placeholder is empty), and isn't committed yet either.
4. **The dataset the headline numbers depend on doesn't ship with the repo.**
   `data/raw/` is entirely gitignored. Anyone who wants to check "99.6%"
   themselves can read the code but can't run it.
5. **What's on disk right now is ahead of what's committed.** The case
   study, the site, three new `pc/` scripts, and a modified `csi_tx/main.c`
   are all uncommitted. `git log` stops five-plus days before the most
   recent data in `data/raw/`.
6. **`csi_cfo` is a dead duplicate of `csi_rx`** (see finding above) — reads
   as a bug or an abandoned feature to anyone who diffs the firmware tree.

**Smallest set of changes that would fix it**, roughly in priority order:

- Commit what's already written (the case study, `site/`, the three new
  scripts, the firmware changes) so `main` matches what's actually being
  claimed publicly. This alone fixes finding #5.
- Trim `README.md` to just setup/architecture/how-to-run, move the narrative
  and results entirely into the case study doc, and put one link at the top
  of the README pointing to it. Link `docs/HANDOFF.md` from the README under
  something like "project history / dev notes" instead of leaving it
  orphaned.
- Either stop tracking `docs/PROMPT_NEXT_SESSION.md` in git (add it to
  `.gitignore`, keep it locally) or rewrite it as human-facing dev
  documentation with the household details removed.
- Move `site/` to its own repository, or add one paragraph at the top of
  `README.md` explaining it's the promotional/portfolio page for this
  project and why it lives here.
- Add a short "Reproducing the results" section to whichever doc becomes
  canonical, stating plainly that `data/raw/` is not included and either
  pointing at a data-availability plan (a sample subset, a request process,
  a release) or explicitly saying results are not independently
  reproducible from the public repo alone.
- Either implement `csi_cfo` as an actually-distinct firmware or delete the
  duplication and describe both nodes as running the same promiscuous
  capture firmware.

---

*This document is a verification pass, not a design doc — it should be
updated or deleted once the numbers above are corrected or re-derived,
not maintained as permanent project documentation.*
