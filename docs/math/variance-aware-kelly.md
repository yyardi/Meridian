# Variance-aware Kelly — registration

**Research agent + Quant B, 2026-09-02. NOTHING COMPUTED FORWARD.** Landed
unmodified. Cohort cutoff is this document's own first commit, read by epoch
from git, never from prose.

## Arm

**Fractional Kelly with a per-entry left tail from B's P(ride) model**, versus
the **incumbent flat fraction**, at **equal mean exposure**, on the forward
shadow tape.

**Model form — features, calibration, LOGO discipline — is pinned by B in a
committed file before the first read. The file is the pin** (rule 12: a pin
declared in prose and not enforced in code is not a pin).

## Metric and gate

Paired per-game **realized log-growth** (primary) and **max-drawdown**
(secondary line), **game-clustered**. **PASS** = log-growth CI excludes zero in
the variance arm's favour at floor.

**Floors:** ≥15 games with ≥1 sizing-divergent entry; ≥100 divergent entries.

**Closure:** 2× floors still straddling → **FAIL-BY-EXHAUSTION.**

## Mandatory printed check — B's pre-committed null, verbatim

**`q5 − q1` realized mean ≈ 0 in-cohort.** If the arm's gain correlates with
mean-selection across quintiles, **the verdict states "rebuilt a filter"
regardless of the primary.**

*This null was pre-committed by the model's own author, before the model was
built. That is why the gate can distinguish a variance model from a filter.*

## Exit-policy condition

**This gate's cohort REQUIRES the incumbent exit policy throughout.** Any
exit-policy change **splits the cohort at that instant** — the source-window
rule applied to policy — because **the flat-quintile premise is
engine-conditional** (see the correction on the dispositions page).

---

**No in-sample result justifies capital. The forward test is the evidence.**

*Results append below this line, never above it.*
