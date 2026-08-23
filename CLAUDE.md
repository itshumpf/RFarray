# csi-array — agent instructions

## Where truth lives

`PROJECT_NOTES.md` (verification pass, 2026-08-02) supersedes any figure in
agent memory **and** any figure in `README.md`. **Do not quote a number about
this project without reading it out of a file in this session.** If you have
not read it, say you don't know.

`docs/DIRECTION.md` (2026-08-15) records intended direction — three channels,
allowlist posture, refused use cases. It is **not a spec and describes nothing
that is built**; never cite it as capability, and never fuse pipeline metrics.

`docs/NODE_CENSUS.md` (2026-08-15) is the evidence-based hardware inventory.
`docs/HANDOFF.md`'s own inventory is dated 2026-07-15 and describes the bench
*after* most of `data/raw/` was captured; read its 15 August correction block
before quoting it.

## The headline numbers, with their condition

Device-ID accuracy is **99.7% over 7,497 windows** (desk receiver alone,
2026-07-13), falling to **95.7% over 14,234 windows** once node3's captures of
those same sessions join the population. The drop is a **cross-receiver
generalization gap, not a harder device population**: in the combined run the
reference beacon's entire test set comes from node3 while its model is trained
87.7% on desk windows. The largest single error mode is 276 reference windows
landing on `84:7b:57:cc:20:0e`, an ambient third-party device 2.54σ from the
reference. **The clock twin `f4:2d:c9:70:72:30` is in neither run** — it first
transmits on 2026-07-14. Quote both numbers with the condition attached, or
quote neither. (`docs/TWIN_INVESTIGATION.md` §6–7.)

- `f4:2d:c9:70:72:30` **is** a genuine clock twin of `a4:f0:0f:77:91:20`:
  0.26σ, ΔSFO 0.00080 rad/sc — **on `rx_20260714_011619.csv`**, where the same
  pair reads 4.29σ on `rx_20260722_204658.csv`. Real and characterized, and
  **not** the cause of the drop above. (`docs/LOT_HYPOTHESIS.md`.)
- The same-model figure (~77%) is a **single-session best case whose class
  count was never recorded**, so it cannot be placed inside the 16.8–80.8%
  range the seven-session three-class sweep measures. Never quote it as
  general performance — and **never relabel it "same-lot."** No purchase,
  serial or lot record exists for any board; that swap trades one unsupported
  claim for another.
- Device-ID (`pc/rff/`, phase domain) and occupancy (`pc/occ/`, amplitude
  domain) are **separate pipelines**. Never combine or cross-cite their
  numbers.

## Failure-mode index

Condensed from `C:\dev\.astory\ERROR_LOG.md`. Read that file for the 27
worked entries; these are the pre-flight checks only.

- **A — prediction printed as measurement.** Every number must be re-derivable
  right now by a command you can name. If you can't name it, label it a guess.
- **B — source judged without being opened.** You may not characterize a source
  you have not retrieved.
- **C — capability failure read as absent data.** Any empty result must
  distinguish *no data exists* / *not allowed to ask* / *never actually asked*.
- **D — secondary source as authority.** Rules, prices and limits come from the
  vendor's own fetched page. A search summary is a pointer, not a source.
- **E — anomaly assumed to be a defect.** Open the record that triggered the
  suspicion before blaming code. Real data is stranger than your imagined bug.
- **F — output never inspected.** Open the finished artifact in the form the
  recipient sees it. The last hour of a project is its worst hour.
- **G — assumed context instead of stated.** Name the field you inferred a
  circumstance from, and whether it actually carries it. If it's a guess, ask.
- **H — superseded artifact asserted as current.** Before quoting any project
  figure, check whether a later artifact supersedes memory. Compare mtimes; a
  verification pass written after the memory file wins.

## Restart hazards

- **`firmware/csi_tx/main/main.c` in the working tree is a BLE diagnostic**
  ("CSI-S3-ALIVE"), not the production beacon. Production beacon = git HEAD.
- **`firmware/csi_cfo/main/main.c` has an uncommitted 2026-08-02 change**
  (`RFF_PROMISCUOUS 0` + hard-coded `TX_FILTER_MAC` = the reference beacon).
  No artifact records it being flashed or verified, and it postdates
  `PROJECT_NOTES.md` by 26 minutes — which is why that file still calls
  `csi_cfo` a duplicate of `csi_rx`. It **fails silently if the reference
  beacon's MAC changes**: the filter is compiled in and the node simply
  captures nothing.
- **`pc/requirements.txt` omits pandas**, which `pc/heatmap.py` imports.
  (scipy is *not* a missing dep — nothing in the repo imports it.)
- **Work at `C:\dev\csi-array`, never the OneDrive copy.** Cloud sync races
  ESP-IDF's `build/` and makes edits appear not to stick.
- Full serial/flashing/COM-port gotchas: **`docs/HANDOFF.md`**, "Hard-won
  gotchas" — read it before touching hardware. Don't restate them from memory.

## Git

Explicit paths only. Never `git add -A`, `git add .`, or `git add --all`.
Never commit. Never push. Braeden does that himself. Staging nothing is fine.
