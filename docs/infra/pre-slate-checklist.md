# Pre-slate checklist — WNBA resumption (first slate ~2026-09-17)

Manager artifact, 2026-09-02. One page, one purpose: the checks that must
pass before and during the first live slate after the ~16-day gap, each with
its command, its expected answer, and what a failure means. Run order is the
section order. The morning-of run is the manager's; items marked FIRST-NIGHT
read only once games are live.

**The freeze pin, cited once for every item below (rule 17):** the running
quote engine is the container started 2026-09-02T16:03:59Z, image built
16:03:57Z from the prod checkout at commit `7a3a217` (tracked tree clean).
`core/quote/` at `7a3a217` is byte-identical to main head as of `0addd69` —
no commits have touched it since. Quoting policy is FROZEN at that commit
until A1's gate reads (quote-v2-program.md, sequencing rule). Any deploy to
the quoter before then is a registration violation, not an ops choice.

## 1. Containers (morning of)

```bash
python scripts/health.py
```

Expected: all containers in the expected dict Up, including the three
overlays (`meridian-pulse-engine`, `meridian-espn-live-recorder`,
`meridian-quote-engine` — the quote engine is RUNNING again since 09-02
16:04Z; its dict annotation was updated in this commit). A missing overlay
is a real outage now, not an operator stop. Remember the health script's
scope: it sees containers and feeds, not correctness — everything else on
this page exists because of that.

## 2. Anchor feed re-verify (first Sept 17 listing)

On the FIRST WNBA listing the venue posts: verify the anchor feed carries it
with sane book lines before tip (books two-sided, spread lines half-point,
YES-frame convention holds: YES = first margin + line > 0). The venue is the
authority — check `api.polymarket.us` responses, not adjacent docs. A
convention change over the gap (new tickers, changed tick size, fee
coefficient) lands here first and silently poisons everything downstream.

## 3. PULSE inter-decision-gap tripwire (FIRST-NIGHT)

The registered cohort ruling's one named channel for quoter-load
contamination: quoter load degrading PULSE cycle times would alter the PULSE
tape itself. Baseline PINNED NOW, from prod `pulse_decisions`
(2026-08-30 → 09-02, gaps < 300s, per-event consecutive decisions,
n = 4,209): **p50 3.218 s · p95 29.870 s · mean 8.019 s.**

No post-16:04Z rows exist yet (no live games since the quoter restart), so
the comparison READS on the first live night — printed, not assumed:

```bash
ssh -i ~/.ssh/meridian-aws.pem ubuntu@$MERIDIAN_SERVER "sudo docker exec -i meridian-postgres psql -U meridian -d meridian -At" <<'SQL'
WITH gaps AS (
  SELECT extract(epoch FROM decided_at - lag(decided_at)
           OVER (PARTITION BY event_slug ORDER BY decided_at)) AS gap,
         (decided_at >= '2026-09-02 16:04:00+00'::timestamptz) AS after
  FROM pulse_decisions
  WHERE decided_at >= '2026-08-30 00:00:00+00'::timestamptz
)
SELECT after, count(*),
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY gap)::numeric, 3),
       round(percentile_cont(0.95) WITHIN GROUP (ORDER BY gap)::numeric, 3)
FROM gaps WHERE gap IS NOT NULL AND gap < 300 GROUP BY after ORDER BY after;
SQL
```

Honest name: this is the INTER-DECISION gap (decisions are written on
actions, not every cycle), not the engine's internal cycle time — but it is
the same instrument on both sides of the comparison, which is what the
tripwire needs. A material p50/p95 degradation with the quoter under load is
the named contamination channel firing; escalate before trusting the night's
PULSE tape for any gated cohort.

## 4. Registered instruments live-check (morning of)

- **Guards** (`core/pulse/guards.py`, deployed): `pulse_abstentions` rows
  should start accruing when games go live. First forward check: refusal
  rate vs the in-sample 3.71%.
- **Crossing arms / mask companion / variance-Kelly / dynamic repricing**:
  all four epochs are pre-Sept-17; they read on accrual. Nothing to run —
  just do not touch their pinned inputs.
- **A1's gate**: substrate is quote-engine real fills; floors ≈3–4 slate
  days. DEPLOYMENT HOLD clause if no fills within 7 days — calendar-check
  it on Sept 24.
- **Quoter**: `shadow_quote_fills` accruing once games are live; the v2
  ledger (A's build) records the full quote stream — verify its first rows
  carry fv, clock-quality, and game_start_time per the registered schema.

## 4b. After ANY engine deploy: the heartbeat ROW advances (10-minute rule)

Promoted from habit to checklist line by amendment 11's rider (2026-09-02,
the night the v2 engine deployed healthy but beat-less): after any engine
deploy, verify the service's `service_heartbeats` row advances within 10
minutes — the ROW, not the log line, because the row is the level every
health surface acts on. The replay-equivalence proof declares this as its
blind spot by design (it compares quoting decisions and fills; liveness
side-effects are outside its comparison set); this check is the named
compensator.

```bash
ssh -i ~/.ssh/meridian-aws.pem ubuntu@$MERIDIAN_SERVER "sudo docker exec meridian-postgres psql -U meridian -d meridian -Atc \"SELECT service, round(extract(epoch from now()-beat_at),1) AS age_s, interval_seconds FROM service_heartbeats ORDER BY service;\""
```

Every deployed engine's age must sit under 3× its interval and SHRINK
back there after a restart. An age that grows while the container logs
look healthy is exactly the 2026-09-02 signature.

## 5. Next fills pin (after first slate)

The next `quote_fills` export must carry `game_start_time` (D1's pregame
fold needs it; the 09-02 pin lacked it). Use the full-column export path
(`scripts/pin_tick_export.sh` gained the fee/book-tier columns for the
survey — same lesson: pin MORE columns than today's question needs).

**League pin (2026-09-02, D's self-reported hazard, export layer owns
it):** `shadow_quote_fills` is mixed-league from GRIDIRON (077c0b9) on.
Every v1-BASELINE export pins `league = WNBA` (event-slug prefix filter,
stated in the export command) — the v1 pin IS the WNBA baseline, and
rule-16 gates count against 17,032 on exactly that cohort; a mixed export
fails those gates closed for the WRONG reason (count mismatch reading as
calibration failure). GRIDIRON exports are separate files with the league
in the filename. The immutable 09-02 pin predates NFL and is already
pure. Consumers' gates stand pat; the filter lives here.

## 6. D1 partition line (owner: Quant D, before its read)

D1's registered pre-read partition predates the quoter stop/restart; its
doc gains one dated line citing the restarted engine: commit `7a3a217`
(container start 2026-09-02T16:03:59Z), `core/quote/` byte-identical to the
Aug-run code as of `0addd69`. Cheap, rule-17 shaped: nobody later asks
which engine's pregame concessions the window measured.

## 7. NBA opening night (~2026-10-20, the event governs)

Separate list, day-one survey runbook + quote-v2 precondition clocks
(amendment 5: any arm uncleared at the review instant converts to
CLOSED-UNMET). Not this page's job; named so it is not forgotten.
