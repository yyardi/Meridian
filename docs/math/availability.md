# Roster availability

**Question:** the model prices season averages for players who may not play tonight. How much is that costing?

The literature says a lot: a star ruled out moves a spread 2–5 points and a total 2–4. That lands on exactly the games where the line moves most. This is Experiment 1 of the v4 ledger.

## The data problem, measured

There is no point-in-time injury history to backtest on. ESPN publishes **current** status only, and this is not an assumption — the `injuries` block inside the summary of a 2025 game returns designations dated 2026. Fetching an old game today tells you who is hurt today.

So the tradable feature can only accrue forward, from the recorder's first run (2026-08-01). Waiting a season to find out whether the idea works is a bad trade, so the experiment runs in two arms:

| Arm | Absence source | Point-in-time? | Tradable? | Purpose |
|---|---|---|---|---|
| `report` | injury change log | Yes | Yes | the real test, forward only |
| `oracle` | tonight's box score | **No** — hindsight | **No** | one-way screen on history |

The oracle arm knows who played by reading the result. It cannot produce an edge number and none of its output may be quoted as one. It answers a single question with a one-way answer:

> A point-in-time model cannot beat its own oracle. If the oracle fails the gate, the tradable version cannot pass it, and the idea dies for the cost of one backfill instead of a season.

Passing proves nothing about tradability. **Failing is the informative outcome**, which is why the arm is worth running at all.

## The adjustment

Nothing is re-projected from scratch. A player-sum projection at WNBA sample sizes is noisier than the team means it would replace, so the team model stands and only the *change* is priced.

For each player, from games strictly before `as_of`:

$$
m_i = \frac{\sum_g w_g \cdot \text{minutes}_{i,g}}{\sum_g w_g}, \qquad
p_i = \frac{\sum_{g:\,\text{played}} w_g \cdot \text{points}_{i,g}}{\sum_{g:\,\text{played}} w_g \cdot \text{minutes}_{i,g}}
$$

with $w_g = 2^{-g/5}$ over the team's last 15 games. Then

$$
\Delta = \underbrace{\sum_{i \,\in\, \text{available}} \left( m_i \cdot \frac{200}{\sum_{\text{available}} m} \right) p_i}_{\text{tonight's lineup}} \; - \; \underbrace{\sum_i m_i p_i}_{\text{the lineup the model assumed}}
$$

Both terms are scaled to 200 team-minutes (5 players × 40), so $\Delta$ measures the lineup change and not the fact that projected minutes rarely sum to exactly 200. The two teams' deltas add: a scorer out on either side lowers the expected combined score.

### Why minutes are zero-filled

$m_i$ averages over **all** the team's recent games, counting zero for ones the player missed — not over the games she played. This is the single most important line in the feature.

A player who has been out for three weeks is already priced into the team's depressed recent form. Deducting her again double-counts and systematically under-projects. Zero-filling decays her projected minutes toward zero, so the second deduction shrinks with the length of the absence and reaches exactly zero once she has missed the whole window. A player who played last night and is ruled out tonight carries her full minutes and takes the full deduction. That distinction is the entire reason the feature exists.

### Known bias

Minutes are conserved and redistributed proportionally, so no replacement-level constant has to be invented. Two errors follow and they point opposite ways:

- Real bench units are worse than a proportional reshuffle of the rotation — **understates** the drop.
- Usage concentrates on the next-best scorers rather than spreading evenly — **overstates** it, most for the biggest stars. A'ja Wilson out prices at ~9 points here, above the 2–4 the literature puts on a star's effect on a total.

Which dominates is unknown, so `availability_beta` scales the whole term and is left for the data to set rather than a guess.

## Result: the gate failed

Seasons 2024–2026, min edge 3.0 pts, β = 1.0, realistic fills. Paired per-game CLV difference on games both arms bet:

| | Oracle − control CLV |
|---|---|
| All shared games | +0.03 [−0.06, +0.12] |
| Absence games only | +0.06 [−0.10, +0.21] |

Both intervals straddle zero. The pre-registered gate required the absence-game interval to exclude it. **Failed.**

The adjustment is not misfiring — the mechanics check out. It fires on 63% of games, which is what ~16 rotation players across two teams at a ~6% individual miss rate implies. Its largest historical value, −40 points, is the 2024 regular-season finale where Las Vegas rested Wilson, Plum, Young and Gray at once. It is finding real absences and pricing them sanely.

## Why it failed, and what that redirects

ROI rose (+1.3% → +6.8%) while CLV did not move. First, the boring part: those ROIs are +1.3% [−11.4%, +14.0%] and +6.8% [−5.0%, +18.7%]. The intervals overlap almost entirely — at n≈250 the "improvement" is not distinguishable from nothing, which is the whole reason [clv.md](clv.md) makes CLV the gate and ROI a diagnostic.

Taking the point estimates at face value anyway, the consistent reading is:

> Lineups are public before tip-off. The closing line already prices them. The information predicts the game but is **not news to the market by close**.

Both numbers would then be the same fact seen twice. Knowing who plays genuinely helps predict the outcome — hence the ROI — but the market knows it too by the time it closes, so there is no better price to be had, hence the flat CLV.

This does not make roster awareness worthless. It relocates its value from *being informed* to *being early* — from a standing feature to a latency question, which is Experiment 4's territory, not this one's. The recorder keeps running: an injury change log with timestamps is the raw material for detecting news windows, and it is unrecoverable if not captured now.

## What was built anyway, and why

The gate failed, but three pieces are kept because they are load-bearing for the window work rather than for this feature:

- `player_game_logs` — 18,076 player-games, 2024–2026. Also the base for any future player-rating work (Experiment 7).
- `injury_reports` + `injury_polls` — the point-in-time change log, accruing from 2026-08-01. Unrecoverable: a poll missed is a poll lost.
- `availability_mode="report"` — the tradable arm, wired and tested, silent until the log has a season in it.

## Status

**Rejected as a standing totals feature** (oracle CLV gate, 2026-08-01). Default is `availability_mode="off"`; the incumbent champion is unchanged. Re-open only if the news-window work shows the market repricing lineups slowly on Polymarket US, which would be a claim about latency, not about the feature above.

---

## Postscript: Experiment 5 (pace interaction) died here too

The ledger proposed replacing the arithmetic mean of team paces with a multiplicative interaction, `league_pace × (paceA/lg) × (paceB/lg)`, on the theory that a fast team amplifies a fast opponent.

Measured on 2025: the multiplicative and additive forms differ by at most **0.05 possessions** — about 0.05 points on a total, against a 3.0-point betting threshold. The backtest results are byte-identical across all 322 bets because no bet ever moves.

The reason is structural, not a failure of the idea: WNBA team pace has a standard deviation of **0.985 possessions** after shrinkage. The two forms agree to first order around the league mean, and the second-order term needs pace dispersion this league does not have. Nothing to fit.
