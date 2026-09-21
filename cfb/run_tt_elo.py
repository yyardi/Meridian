"""Fit the registered table-tennis Elo and report it PER COMPETITION.

    PYTHONPATH=. DATABASE_URL=... python cfb/run_tt_elo.py \
        --settlements /opt/meridian/artifacts/reads/settlements.json
    # or --tsv slug<TAB>y<TAB>price_yes<TAB>started_at  (one match per line)

`PYTHONPATH=.` is required and is not decoration: run as `python cfb/...`,
sys.path[0] is `cfb/` rather than the repo root, so `core.tt` does not resolve
and `core` may come from an installed copy instead of the checkout. Every
`cfb/run_*.py` shares this; it is the local form of "a long-lived container is
not the repo".

Registered spec: docs/math/tabletennis-rating-preregistration.md.
Specifications and the pre-committed decision rule:
docs/math/tabletennis-elo-harness.md.

It must run TODAY, when zero matches are eligible, and say so rather than
raise. A harness that only works once the data is sufficient is a harness
debugged on the day it matters.

NEVER POOLED. The four competitions are different leagues; pooling them is
named in the pre-registration as the error that produced three false
descriptions in one day. `setkawoua` is reported separately again, because its
6-player pool cannot meet the >=25 floor and NOT YET is its only reachable
verdict.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import defaultdict

from core.tt import elo, money, rule

COMPETITIONS = ("setkameua", "setkamecz", "setkamemd", "setkawoua")

#: Prices and start times for the settled slugs. Equality on market_slug uses
#: the unique (market_slug, captured_at) index, and the month-boundary floor
#: prunes partitions -- an unbounded version of this seq-scans 62M rows.
#: slug -> (best_bid, best_ask) at the LAST pregame quote. The money arm needs
#: the EXECUTABLE sides, not the mid: you buy YES at the ask and NO at 1-bid,
#: and charging a mid would understate the bar by the half-spread. Populated by
#: load_db only -- load_tsv has no book, which is why the money arm reports
#: "no book" rather than silently scoring zero bets.
BOOKS: dict[str, tuple[float, float]] = {}

PRICE_SQL = """
SELECT DISTINCT ON (market_slug) market_slug,
       (best_bid + best_ask) / 2.0 AS mid, best_bid, best_ask, game_start_time
FROM market_snapshots
WHERE market_slug = ANY(:slugs)
  AND captured_at >= CAST(:since AS timestamptz)
  AND best_bid IS NOT NULL AND best_ask IS NOT NULL
  AND game_start_time IS NOT NULL
  AND captured_at < game_start_time
ORDER BY market_slug, captured_at DESC
"""


def load_tsv(path: str) -> list[elo.Match]:
    """slug, y, price_yes, started_at (ISO). Blank price or time is kept as
    None so the replay can refuse and COUNT it."""
    out = []
    for line in open(path):
        if not line.strip():
            continue
        slug, y, price, started = (line.rstrip("\n").split("\t") + ["", "", ""])[:4]
        parsed = elo.parse_slug(slug)
        if parsed is None:
            print(f"  UNPARSED (counted, not dropped): {slug}", file=sys.stderr)
            continue
        comp, p1, p2 = parsed
        out.append(elo.Match(
            slug, comp, p1, p2, int(y),
            dt.datetime.fromisoformat(started) if started else None,
            float(price) if price else None))
    return out


def load_db(settlements: str, since: str = "2026-09-01") -> list[elo.Match]:
    from sqlalchemy import create_engine, text

    book = json.load(open(settlements))
    keep = {k: int(v) for k, v in book.items()
            if k.split("-")[1:2] and k.split("-")[1] in COMPETITIONS}
    eng = create_engine(os.environ["DATABASE_URL"])
    with eng.connect() as c:
        rows = {r._mapping["market_slug"]: r._mapping for r in c.execute(
            text(PRICE_SQL), {"slugs": sorted(keep), "since": since})}

    out, unparsed = [], 0
    for slug, y in sorted(keep.items()):
        parsed = elo.parse_slug(slug)
        if parsed is None:
            unparsed += 1
            continue
        comp, p1, p2 = parsed
        r = rows.get(slug)
        out.append(elo.Match(slug, comp, p1, p2, y,
                             r["game_start_time"] if r else None,
                             float(r["mid"]) if r else None))
        if r is not None and r["best_bid"] is not None and r["best_ask"] is not None:
            BOOKS[slug] = (float(r["best_bid"]), float(r["best_ask"]))
    if unparsed:
        print(f"  UNPARSED (counted, not dropped): {unparsed}")
    return out


def load_state(path: str | None) -> dict[str, str] | None:
    """Last run's verdict per competition, or None when there is no state yet.

    None and {} are DIFFERENT and the difference is the whole point: on the
    first run there is no previous verdict, so nothing is a transition and
    nothing is pushed. A missing file read as "everything changed" would push
    four NOT YETs the first night, which is how a channel earns being ignored
    before it ever carries the one message that matters.
    """
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path) as fh:
            got = json.load(fh)
        return {str(k): str(v) for k, v in got.get("verdicts", {}).items()}
    except (json.JSONDecodeError, OSError, AttributeError) as exc:
        print(f"  state file unreadable ({exc}); treating as FIRST RUN, so no "
              "transition is reported this time")
        return None


def save_state(path: str, verdicts: dict[str, str]) -> None:
    """Temp file plus os.replace: a run killed mid-write leaves the old state,
    never a truncated file that the next run reads as a first run."""
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w") as fh:
        json.dump({"at": dt.datetime.now(dt.timezone.utc).isoformat(),
                   "verdicts": verdicts}, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)


def transitions(previous: dict[str, str] | None, now: dict[str, str]
                ) -> list[str]:
    """One line per competition whose verdict CHANGED. Empty on a first run."""
    if previous is None:
        return []
    return [f"{c}: {previous[c]} -> {v}" for c, v in sorted(now.items())
            if c in previous and previous[c] != v]


def _money_line(preds) -> str:
    """One line for the money arm, whatever state it is in.

    Four states, all printed rather than skipped: no book loaded (a --tsv run),
    no eligible predictions yet, eligible but nothing clears its own price, and
    a scored result. The first three are NOT YET and say why.
    """
    if not BOOKS:
        return "NOT YET  no book loaded (--tsv run has no bid/ask)"
    if not preds:
        return "NOT YET  0 eligible predictions"
    bets, a, b = [], [], []
    for pr in preds:
        bk = BOOKS.get(pr.slug)
        if bk is None:
            continue
        bet = money.bet(pr.slug, pr.elo_p, bk[0], bk[1], pr.y)
        if bet is not None:
            bets.append(bet)
            a.append(pr.p1)
            b.append(pr.p2)
    if not bets:
        return (f"NOT YET  0 of {len(preds)} eligible cleared their own price "
                f"(book on {sum(1 for pr in preds if pr.slug in BOOKS)})")
    r = money.summarise(bets, a, b)

    # The verdict comes from the REGISTERED rule, not from an expression here.
    # The inline version this replaces returned PASS on `hi < 0` -- an interval
    # entirely BELOW zero, which is a strategy that reliably loses, printed as a
    # pass. It also tested "excludes zero" BEFORE the sample-size gate, so a
    # degenerate interval at n=5 could PASS, which is exactly the protection
    # §7's achievable image exists to provide.
    #
    # The gate's target is the cost this arm ACTUALLY PAID, not a population
    # constant. That bar was measured four times in nine days and moved every
    # time -- the board went 724 -> 1,339 markets, the median half-spread
    # halved while its mean nearly doubled, and the venue's coefficient went
    # 0.06 -> 0.0695 underneath. Two published constants from it are already
    # retracted (core/tt/money.py says why), so a fifth would be the pattern
    # rather than the answer.
    #
    # Realised MEDIAN is the stricter gate (a narrower interval is demanded)
    # and realised MEAN the looser, because the cost distribution has a long
    # right tail of wide-quoted matches. The verdict is read from the strict
    # end; the loose end is printed so the choice is visible rather than
    # implied by whichever number the caller happened to pass.
    strict_bar, loose_bar = r.cost_median, r.cost_mean
    strict = money.required_n(resolution=strict_bar)
    loose = money.required_n(resolution=loose_bar)
    verdict, why = rule.money_verdict(
        n=len(bets), lo=r.lo, hi=r.hi,
        resolution=strict_bar, required=strict)
    at_loose, _ = rule.money_verdict(
        n=len(bets), lo=r.lo, hi=r.hi,
        resolution=loose_bar, required=loose)
    both = "" if at_loose == verdict else f"  ({at_loose} at the mean cost)"
    return (f"{verdict}  n={len(bets)} net {r.mean * 100:+.2f}c "
            f"player-clustered [{r.lo * 100:+.2f},{r.hi * 100:+.2f}]  "
            f"realised cost mean {loose_bar * 100:.2f}c "
            f"median {strict_bar * 100:.2f}c  "
            f"({why}; need ~{strict} to resolve the {strict_bar * 100:.2f}c it "
            f"paid, ~{loose} at {loose_bar * 100:.2f}c){both}")


def report(matches: list[elo.Match], state_path: str | None = None) -> int:
    cross = elo.cross_competition_tokens(matches)
    if cross:
        print("  TOKEN IN MORE THAN ONE COMPETITION -- identity already treats "
              "these as separate players; the two definitions have now DIVERGED:")
        for t, comps in cross.items():
            print(f"    {t}: {comps}")
    else:
        print("  no token appears in more than one competition (the two "
              "prior-match definitions remain indistinguishable)")

    verdicts: dict[str, str] = {}
    by_comp: dict[str, list[elo.Match]] = defaultdict(list)
    for m in matches:
        by_comp[m.competition].append(m)

    print(f"\n  {'competition':12s} {'settled':>7s} {'players':>7s} "
          f"{'eligible':>8s} {'verdict':>8s}  reason")
    worst = 0
    for comp in COMPETITIONS:
        ms = by_comp.get(comp, [])
        if not ms:
            print(f"  {comp:12s} {'0':>7s} {'0':>7s} {'0':>8s} {'NOT YET':>8s}"
                  "  no settled matches")
            continue
        preds = elo.replay(ms)
        ok = [p for p in preds if p.eligible]
        players = {p.p1 for p in ms} | {p.p2 for p in ms}
        priced = [p for p in ok if p.price_yes is not None]

        excludes = False
        extra = ""
        if len(priced) >= 2 and len({p.y for p in priced}) > 1:
            from core.tt.fit import fit
            f = fit([p.price_yes for p in priced], [p.elo_p for p in priced],
                    [p.y for p in priced], [p.p1 for p in priced],
                    [p.p2 for p in priced])
            excludes = f.excludes_zero(2, "game")
            lo, hi = f.ci(2, "game")
            lo2, hi2 = f.ci(2, "player")
            extra = (f"\n      elo beta {f.beta[2]:+.4f}  "
                     f"game-clustered [{lo:+.3f},{hi:+.3f}] (REGISTERED)  "
                     f"player-clustered [{lo2:+.3f},{hi2:+.3f}]  "
                     f"deff {f.deff(2):.2f}  G_eff {f.g_eff(2):.0f}")
        v, why = rule.verdict(predicted=len(ok), players=len(players),
                              interval_excludes_zero=excludes)
        note = ""
        if rule.reachable(max_predicted=10 ** 6,
                          max_players=len(players)) == {rule.NOT_YET}:
            note = ("  <-- pool of %d cannot EVER meet the >=%d-player floor"
                    % (len(players), rule.MIN_PLAYERS))
        print(f"  {comp:12s} {len(ms):7d} {len(players):7d} {len(ok):8d} "
              f"{v:>8s}  {why}{note}{extra}")
        verdicts[comp] = v

        # THE MONEY ARM. Runs ALWAYS, never gated on the signal verdict:
        # conditioning it on a signal PASS would select on the same outcomes
        # the signal was read from. It is a SEPARATE verdict and is never
        # collapsed into the one above -- a SIGNAL-yes MONEY-no result is a
        # real finding, not a failure. Printed on every run even at zero bets,
        # because a registered criterion that prints nothing is registered in
        # name only (it was library-only and uncalled until 2026-09-15).
        print(f"      MONEY  {_money_line(ok)}")
    print("\n  NOT YET is not a FAIL. It means a floor is unmet; the counts "
          "above are the report the registered spec asks for.")

    # THE WHOLE POINT OF BUILDING THREE DAYS EARLY: nobody has to be watching.
    # Every night prints the counts; only a CHANGED verdict is worth waking
    # someone for, so the transition line is what the wrapper greps for.
    if state_path:
        previous = load_state(state_path)
        moved = transitions(previous, verdicts)
        if previous is None:
            print(f"  state recorded for the first time in {state_path}; "
                  "no transition by definition")
        elif moved:
            for line in moved:
                print(f"  TT ELO TRANSITION {line}")
        else:
            print("  no verdict changed since the last run")
        save_state(state_path, verdicts)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--settlements")
    ap.add_argument("--tsv")
    ap.add_argument("--state", help="JSON of the last run's verdicts; a CHANGED "
                                    "verdict prints a TT ELO TRANSITION line")
    ap.add_argument("--since", default="2026-09-01",
                    help="month boundary; a mid-month floor filters without pruning")
    a = ap.parse_args()
    if a.tsv:
        matches = load_tsv(a.tsv)
    elif a.settlements:
        matches = load_db(a.settlements, a.since)
    else:
        ap.error("one of --tsv or --settlements")
    print(f"table-tennis Elo, K={elo.K_DEFAULT:g}, start {elo.START_RATING:g}, "
          f">={elo.MIN_PRIOR_MATCHES} prior in the same competition")
    print(f"  {len(matches)} settled matches parsed")
    return report(matches, a.state)


if __name__ == "__main__":
    raise SystemExit(main())
