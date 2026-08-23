# Direction — 15 August 2026

> **THIS IS NOT A SPEC. NOTHING IN THIS FILE IS BUILT.**
> This document records where the project is *pointed*. It is a mix of
> decisions and open exploration, and every item below is explicitly
> tagged **[DECIDED]** or **[EXPLORED]**. If you find yourself quoting
> this file as evidence that the system does something, stop — that is
> failure mode **A** (prediction printed as measurement) and this
> project has hit it before. For what actually exists and what it
> actually measures, read `PROJECT_NOTES.md` and `docs/HANDOFF.md`.

**Provenance.** This came out of a conversation on 2026-08-15 between
Braeden and an assistant. The BLE intent and the camera-deadzone
application are Braeden's. Nothing here has been validated, prototyped,
costed, or committed to. It is a written record of intent so that it
stops living only in one person's head.

---

## 1. Three identification channels against one allowlist

**[DECIDED]** — as an architecture, not as a delivered capability.

| channel | domain | status |
|---|---|---|
| WiFi CFO/SFO fingerprinting (`pc/rff/`) | phase | **built and measured** |
| CSI occupancy (`pc/occ/`) | amplitude | **built and measured** |
| BLE | — | **tabled.** Groundwork exists, uncommitted, in `firmware/csi_tx/` since 2026-07-22 |

BLE was deliberate groundwork toward a third channel, not debris from
the S3 WiFi-TX investigation. See the 15 August 2026 correction in
`docs/HANDOFF.md` under *Hard-won gotchas*. It is **not started** as a
channel: no enrollment, no scanner firmware, no PC-side pipeline.

## 2. The high-value signal is the combination

**[DECIDED]** as the thing worth building toward. **[EXPLORED]** as to
how it is actually computed — no fusion logic exists.

The signal of interest is **a body present with no enrolled device.**
Neither existing pipeline detects that alone:

- **Device fingerprinting alone misses people.** Anyone who left a
  phone behind, powered it off, or went deliberately dark is invisible
  to it.
- **Occupancy alone cannot tell authorized from unauthorized.** It
  reports that a room is occupied, not by whom.

The conjunction — occupancy positive, allowlist match negative — is
what neither channel produces on its own.

### The numbers rule still applies, and applies harder here

Device-ID (`pc/rff/`, phase domain) and occupancy (`pc/occ/`, amplitude
domain) may be **fused at inference time**. Their **accuracy figures
must never be fused into a single headline number.** There is no
measured joint accuracy for the conjunction above and there will not be
one until it is built and scored against labeled data.

**Fusing signals is the design. Fusing metrics is the error.** Quote
device-ID accuracy with its condition, quote occupancy rates with their
protocol caveats, and never multiply, average, or blend them into one
figure. See `CLAUDE.md` for the exact figures and the conditions that
must travel with them.

## 3. Allowlist, not census

**[DECIDED].** This is a design and legal posture, not an
implementation detail.

The system is built to **detect absence from a known set**, not to
identify individuals. Enrolled devices are known. Everything else is an
unknown to be flagged as an unknown — not resolved, not named, not
attributed to a person.

This is the difference between "an unenrolled device is present" and
"we know who that is." The second one is not the product and is not a
capability to be added later.

## 4. Target application: camera deadzones

**[DECIDED]** as the application to aim at. **[EXPLORED]** as to
whether it works there — no deployment, no field trial, no customer.

Physical security coverage in **camera deadzones**: server rooms,
wiring closets, stairwells, loading docks, storage. Places where
cameras are unavailable — for cost, privacy, sightline, or policy
reasons — and where RF presence is the least invasive form of
visibility that exists. A CSI array sees that someone is there; it does
not see who they are or what they look like.

## 5. Out of scope — refused, not merely unimplemented

**[DECIDED].**

**Workforce monitoring, attendance tracking, and productivity
measurement are refused use cases.** Not "not built yet," not "a
possible future module." The allowlist-not-census posture in §3 exists
partly to make this structurally hard rather than merely
policy-forbidden. If a future request would require resolving presence
to a named person over time, that request is out of scope and this
paragraph is the reason.

## 6. Retention posture

**[DECIDED]** as intent. **[EXPLORED]** as implementation — the current
tooling does **not** do this. `pc/capture.py` records raw CSI and
`data/rff.db` accumulates history; nothing today enforces the policy
below.

**Fingerprint, count, discard.** Raw frames are not retained for
non-allowlisted devices. What persists for an unknown is that it was
seen and counted, not the material to re-identify it later.

## 7. Known limit, stated up front

**[DECIDED]** — this is a limit to be disclosed, not solved.

**This identifies devices, not people.** Every claim the system makes
is about radios. A person carrying two enrolled devices is two entries;
a person carrying none is invisible to the device channel entirely
(which is precisely why §2 exists). Any deployment description that
elides this is overselling.

---

## What would have to happen next

**[EXPLORED]** — none of this is scheduled or committed.

- BLE channel: commit the existing groundwork, then decide scanner vs.
  advertiser role, enrollment model, and PC-side pipeline. Nothing
  beyond the uncommitted firmware exists.
- Fusion logic for §2: does not exist. Would need a labeled protocol of
  its own, in the spirit of `docs/OCC_PROTOCOL.md`, before any joint
  number is quotable.
- Retention enforcement for §6: does not exist in `pc/`.
- The camera-deadzone application has not been tested in a
  camera-deadzone environment.
