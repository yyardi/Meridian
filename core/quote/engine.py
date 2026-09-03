"""The QUOTE shadow engine: a maker that never places anything.

What it is
----------
One shadow maker per quotable market: a bid resting at the venue's best bid
and an offer at the best ask, one contract each, requoted to the touch every
cycle. Everything is derived from the recorded snapshot stream this repo
already writes — the engine makes **no venue call for market data and no
authenticated call at all**; its only network touch is the public settlement
endpoint, explicit answers only.

**No order exists anywhere in this module and none can.** There is no import
path to `core.executor` or `core.polymarket.client`'s order class — pinned by
an AST-level test, the same structural guarantee the live-FV strip and the EV
guard carry. The kill switch, the CHECK constraints and `orders_autonomous`
are all untouched because nothing here goes near them.

Why it exists (docs/math/quote-shadow.md — the registration)
------------------------------------------------------------
The static adverse-selection study already measured naive quoting as a loser
in both regimes (−2.74¢/fill in-game, −0.86¢ pregame — C13's inputs). What it
could not price is **requoting**: its quotes are born at one snapshot and
marked at a fixed horizon. A real maker pulls and follows the touch. This
engine measures quoting under that one added behaviour, with everything else
held identical to the study — same quotable band, same fill rule, same
clustering — so any difference is attributable to requoting and nothing else.

The fill rule and its signed bias
---------------------------------
A standing bid fills when a NEWER observation's mid reaches it
(``mid <= bid``); an offer when ``mid >= ask``. This is the study's own rule
and shares its known optimism: between observations there is no path, so a
transient dip that fills you and recovers is invisible — the undercounted
fills are exactly the ones that hurt. Therefore a measured loss is
trustworthy and a measured profit is an upper bound that authorises nothing.

Scoring is not done here. The engine records fills; ``core/quote/report.py``
scores them at settlement, money-at-price (C11), clustered by game (C4),
behind pre-registered floors.
"""

from __future__ import annotations

import datetime as dt
import os
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal

import structlog
from sqlalchemy import text

from core import heartbeat as hb
from core.leagues import league_of_slug, strict_default_league
from core.quote.adverse_selection import Quote
from core.quote.storage import ASK, BID, INGAME, PREGAME, ShadowQuoteFill

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc


#: The env the writer reads for its commit stamp. The Dockerfile takes
#: `ARG GIT_COMMIT` and bakes it as this env at BUILD time, so a container
#: always carries its image's commit and a plain `up -d` can't stamp a checkout
#: commit onto older code. The writer reads the BAKED name, never the build-arg.
ENGINE_COMMIT_ENV = "MERIDIAN_ENGINE_COMMIT"


def require_engine_commit() -> str:
    """The writing binary's git commit, from MERIDIAN_ENGINE_COMMIT (the
    GIT_COMMIT build-arg baked into the image at build time; amendment 12).
    FAIL-CLOSED: the engine refuses to start without it — a NULL provenance stamp
    defeats the amendment whose whole job is provenance. Read at start and
    stamped on every fill/observation row."""
    commit = (os.environ.get(ENGINE_COMMIT_ENV) or "").strip()
    if not commit:
        raise RuntimeError(
            f"{ENGINE_COMMIT_ENV} is absent — the quote engine refuses to start "
            "(amendment 12: every fill/observation row stamps its binary; build "
            "the image with --build-arg GIT_COMMIT=$(git rev-parse HEAD), which "
            f"bakes {ENGINE_COMMIT_ENV}).")
    return commit

#: Heartbeat service name. Defined here rather than in core/heartbeat.py,
#: which was carrying another session's uncommitted work when this shipped —
#: add to APP_DB_SERVICES there when the file is clean, so /api/status and
#: scripts/health.py judge the beat (docs/math/quote-shadow.md, ops notes).
SERVICE_QUOTE = "quote_engine"


def service_quote_for(league: str) -> str:
    """The heartbeat / health key for a league's quote engine. WNBA keeps the
    bare historical name (deployed and monitored on `quote_engine` since before
    amendment 12); every other league is suffixed so its engine writes its OWN
    heartbeat row and cannot collide with or overwrite WNBA's. GRIDIRON (nfl)
    therefore beats as `quote_engine_nfl` and is independently visible to
    /api/status and scripts/health.py. 'wnba' is hardcoded as the bare-name
    league deliberately — the key is an identity, not an env-derived default, so
    it must not shift if MERIDIAN_LEAGUE's default ever changes."""
    return SERVICE_QUOTE if league == "wnba" else f"{SERVICE_QUOTE}_{league}"

#: Cycle cadence. 5s sees every requote-worthy move on the 1s tick stream
#: without hammering the database; the fill rule is endpoint-based either way.
DEFAULT_INTERVAL_SECONDS = float(os.environ.get("MERIDIAN_QUOTE_INTERVAL_SECONDS", "5"))
#: How often the settlement sweep runs.
DEFAULT_SETTLE_EVERY_SECONDS = float(
    os.environ.get("MERIDIAN_QUOTE_SETTLE_EVERY_SECONDS", "600"))

#: Only observations this fresh may fill or seed a quote. A market whose
#: stream has gone quiet is a market we are not quoting — a stale book that
#: "fills" hours later would be a fiction.
MAX_OBSERVATION_AGE_SECONDS = 600.0

#: Fills younger than this are not asked about at settlement — WNBA markets
#: settle hours after the fills, and asking early is quota for nothing.
MIN_SETTLE_AGE_HOURS = 4.0


@dataclass(frozen=True)
class Observation:
    """One market's latest two-sided book, from the recorded stream."""

    market_slug: str
    game_id: str
    captured_at: dt.datetime
    bid: float
    ask: float
    is_live: bool

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def is_quotable(self) -> bool:
        # The study's own band, via its own class — one definition of quotable.
        return Quote(
            game_id=self.game_id, market_slug=self.market_slug,
            captured_at=self.captured_at, bid=self.bid, ask=self.ask,
        ).is_quotable


@dataclass(frozen=True)
class StandingQuote:
    """Our two resting shadow prices on one market, born at one observation."""

    market_slug: str
    game_id: str
    regime: str                  # fixed at birth: the regime that decided to rest
    bid_price: float
    ask_price: float
    mid: float
    spread: float
    quoted_at: dt.datetime


@dataclass
class CycleResult:
    observed: int = 0
    quoted: int = 0
    fills: int = 0
    requotes: int = 0
    settled: int = 0


class ShadowQuoter:
    """The engine. Read-mostly; its writes are `shadow_quote_fills` rows and
    one heartbeat, all into its own database."""

    def __init__(
        self,
        sessionmaker,
        *,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
        settle_every_seconds: float = DEFAULT_SETTLE_EVERY_SECONDS,
        settlement_lookup=None,
        league: str | None = None,
    ) -> None:
        self._Session = sessionmaker
        self.interval_seconds = interval_seconds
        self.settle_every_seconds = settle_every_seconds
        #: This binary's league (amendment 12). The frozen binary is WNBA; the
        #: GRIDIRON binary is this same engine with league='nfl'. The engine
        #: observes and quotes ONLY this league; the filter is on the read path
        #: (_observations) AND the write path (_fill). Default from MERIDIAN_LEAGUE.
        # strict_default_league RAISES on an unknown MERIDIAN_LEAGUE rather
        # than silently becoming a second WNBA quoter (2026-09-03 incident).
        self._league = (league or strict_default_league().slug)
        #: This binary's commit (amendment 12), stamped on every row. None only
        #: in tests that don't set the env; run_forever fail-closes in prod.
        self._engine_commit = (
            os.environ.get(ENGINE_COMMIT_ENV) or "").strip() or None
        #: slug -> bool|None ("settled to what?"). Production asks the PUBLIC
        #: gateway; tests inject. Explicit 0/1 only; anything else is not an
        #: answer (the fill-watcher lesson).
        self._settlement_lookup = settlement_lookup or self._venue_settlement
        self._standing: dict[str, StandingQuote] = {}
        self._last_settle = float("-inf")
        self._heartbeat = hb.Heartbeat(sessionmaker, service_quote_for(self._league))
        self._stop = threading.Event()

    # ---- data in ---------------------------------------------------------- #

    def _observations(self, session) -> list[Observation]:
        rows = session.execute(text("""
            SELECT DISTINCT ON (market_slug)
                   market_slug, game_id, captured_at, best_bid, best_ask, is_live
            FROM market_snapshots
            WHERE best_bid IS NOT NULL AND best_ask IS NOT NULL
              AND game_id IS NOT NULL
              AND captured_at > now() - make_interval(secs => :age)
            ORDER BY market_slug, captured_at DESC
        """), {"age": MAX_OBSERVATION_AGE_SECONDS}).all()
        out = []
        for r in rows:
            lg = league_of_slug(r.market_slug)
            if lg is None or lg.slug != self._league:
                continue              # league filter (amendment 12), READ path:
                                      # this binary observes only its own league;
                                      # an unknown/other-league slug is dropped.
            bid, ask = float(r.best_bid), float(r.best_ask)
            if ask <= bid:
                continue              # crossed/locked: nothing rests inside that
            out.append(Observation(
                market_slug=r.market_slug, game_id=str(r.game_id),
                captured_at=r.captured_at, bid=bid, ask=ask,
                is_live=bool(r.is_live),
            ))
        return out

    # ---- one cycle -------------------------------------------------------- #

    def cycle(self) -> CycleResult:
        """Fill-check every standing quote against newer observations, then
        requote to the touch. Public so tests drive it directly."""
        result = CycleResult()
        with self._Session() as s:
            observations = self._observations(s)
            result.observed = len(observations)

            fills: list[ShadowQuoteFill] = []
            seen: set[str] = set()
            for ob in observations:
                seen.add(ob.market_slug)
                standing = self._standing.get(ob.market_slug)

                # 1. Fills first, against the quote that was ALREADY resting —
                #    a quote cannot be filled by the observation it was born
                #    from, and a fill is judged at the old price even when this
                #    same observation moves the touch (that ordering is the
                #    whole requoting question).
                if standing is not None and ob.captured_at > standing.quoted_at:
                    mid = ob.mid
                    if mid <= standing.bid_price:
                        fills.append(self._fill(standing, ob, BID))
                    if mid >= standing.ask_price:
                        fills.append(self._fill(standing, ob, ASK))

                # 2. Requote at the current touch (or stand down if the market
                #    left the quotable band — a maker does not quote a 20¢
                #    spread just because it used to be 3¢).
                if ob.is_quotable:
                    moved = (
                        standing is None
                        or standing.bid_price != ob.bid
                        or standing.ask_price != ob.ask
                    )
                    if moved:
                        result.requotes += int(standing is not None)
                        self._standing[ob.market_slug] = StandingQuote(
                            market_slug=ob.market_slug, game_id=ob.game_id,
                            regime=INGAME if ob.is_live else PREGAME,
                            bid_price=ob.bid, ask_price=ob.ask,
                            mid=ob.mid, spread=ob.ask - ob.bid,
                            quoted_at=ob.captured_at,
                        )
                else:
                    self._standing.pop(ob.market_slug, None)

            # Markets that stopped producing observations stop being quoted.
            for slug in list(self._standing):
                if slug not in seen:
                    del self._standing[slug]

            for f in fills:
                s.add(f)
            s.commit()
            result.quoted = len(self._standing)
            result.fills = len(fills)

        if time.monotonic() - self._last_settle >= self.settle_every_seconds:
            self._last_settle = time.monotonic()
            result.settled = self._settle_fills()
        return result

    def _fill(self, standing: StandingQuote, ob: Observation, side: str) -> ShadowQuoteFill:
        lg = league_of_slug(standing.market_slug)
        if lg is None or lg.slug != self._league:
            # league filter (amendment 12), WRITE path — a should-never-fire
            # guard (the read path already dropped other-league slugs), so if it
            # ever fires the binary is out of contract and must not write.
            raise RuntimeError(
                f"league filter (write path): {self._league} binary refused to "
                f"fill {standing.market_slug} "
                f"(routes to {lg.slug if lg else None})")
        price = standing.bid_price if side == BID else standing.ask_price
        log.info(
            "shadow_quote_fill",
            market=standing.market_slug, side=side, regime=standing.regime,
            price=price, mid_at_fill=ob.mid,
            rested_seconds=round(
                (ob.captured_at - standing.quoted_at).total_seconds(), 1),
        )
        return ShadowQuoteFill(
            market_slug=standing.market_slug,
            game_id=standing.game_id,
            regime=standing.regime,
            side=side,
            quote_price=Decimal(str(price)),
            mid_at_quote=Decimal(str(round(standing.mid, 4))),
            spread_at_quote=Decimal(str(round(standing.spread, 4))),
            mid_at_fill=Decimal(str(round(ob.mid, 4))),
            quoted_at=standing.quoted_at,
            filled_at=ob.captured_at,
            engine_commit=self._engine_commit,
        )

    # ---- settlement ------------------------------------------------------- #

    def _venue_settlement(self, market_slug: str) -> int | None:
        """The public gateway's answer, or None. Never a guess."""
        from core.polymarket.client import PolymarketGatewayClient

        try:
            with PolymarketGatewayClient() as gw:
                body = gw.get_settlement(market_slug)
            value = body.get("settlement")
            return value if value in (0, 1) else None
        except Exception as exc:
            log.warning("quote_settlement_check_failed",
                        market=market_slug, error=str(exc)[:150])
            return None

    def _settle_fills(self) -> int:
        """Mark old unsettled fills with the venue's explicit answer."""
        cutoff = dt.datetime.now(UTC) - dt.timedelta(hours=MIN_SETTLE_AGE_HOURS)
        with self._Session() as s:
            slugs = [r[0] for r in s.execute(text("""
                SELECT DISTINCT market_slug FROM shadow_quote_fills
                WHERE settlement IS NULL AND filled_at < :cutoff
            """), {"cutoff": cutoff}).all()]
        settled = 0
        for slug in slugs:
            answer = self._settlement_lookup(slug)
            if answer not in (0, 1):
                continue
            with self._Session() as s:
                s.execute(text("""
                    UPDATE shadow_quote_fills
                    SET settlement = :v, settled_at = now()
                    WHERE market_slug = :m AND settlement IS NULL
                """), {"v": answer, "m": slug})
                s.commit()
            settled += 1
            log.info("shadow_quote_fills_settled", market=slug, settlement=answer)
        return settled

    # ---- lifecycle -------------------------------------------------------- #

    def stop(self) -> None:
        self._stop.set()

    def run_forever(self) -> None:
        # FAIL-CLOSED (amendment 12): refuse to start without a commit stamp, so
        # no unstamped row can ever be written in production.
        self._engine_commit = require_engine_commit()
        log.info("quote_engine_started",
                 interval_seconds=self.interval_seconds, league=self._league,
                 engine_commit=self._engine_commit,
                 note="shadow only — no order exists behind anything this writes")
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                result = self.cycle()
                any_live = any(
                    q.regime == INGAME for q in self._standing.values())
            except Exception as exc:   # one bad cycle must not kill the run
                log.error("quote_engine_cycle_failed", error=str(exc)[:300])
                result, any_live = CycleResult(), None
            self._heartbeat.beat(
                interval_seconds=self.interval_seconds,
                rows_written=result.fills,
                cycle_seconds=time.monotonic() - started,
                game_live=any_live,
            )
            self._stop.wait(self.interval_seconds)


def main() -> int:
    from core.storage import get_engine, get_sessionmaker

    ShadowQuoter(get_sessionmaker(get_engine())).run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
