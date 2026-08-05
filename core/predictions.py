"""Prediction logger — the system's own dataset.

Every fair value the model emits is written here with the live market price and
a timestamp; the resolution job fills in the outcome later. That log **is** the
long-run dataset, and it compounds daily.

The question it exists to answer, at any moment:

    "How would every prediction I have ever made have performed?"

Two rules that make that answerable rather than merely plausible:

* **Log everything, not just actionable predictions.** No-edge predictions are
  the control group. Without them you cannot distinguish a skilled model from
  selective memory. `is_actionable` is a flag, not a filter.
* **Append-only.** A prediction's model price is never rewritten. Only the
  resolution fields are filled in later.
* **An anchor must be fresh, not merely present.** A prediction is only
  actionable if the freshest non-live book row for its game is under 60
  minutes old at prediction time (`MAX_ANCHOR_AGE_SECONDS`). The threshold is
  pre-registered — chosen 2026-08-05, before any measurement against it: the
  fast leg polls book lines every 20 minutes, so 60 minutes is three
  consecutive missed polls, a feed that is down rather than one between
  cycles. The 2026-08-04 ESPN odds outage (6 hours) happened to fall between
  games; this guard exists so the next one produces no-bets instead of bets
  anchored to an hours-old number. Stale-anchored predictions are still
  logged — same rule as unanchored ones — just never actionable.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from core.storage import (
    MarketSnapshot,
    Prediction,
    SportsbookOdds,
    get_engine,
    get_sessionmaker,
)
from core.board import is_pregame, latest_snapshot_per_market, snapshot_age_seconds
from core.feeds.espn_client import ESPNClient
from core.team_mapping import (
    UnknownTeamError,
    orient_for_slug,
    orientation_from_scoreboard,
    parse_market_slug,
)
from strategies.wnba_totals.config import CONFIG, WNBATotalsConfig
from strategies.wnba_totals.model.fair_value import (
    MARKET_SPREAD,
    MARKET_TOTAL,
    MARKET_WINNER,
    estimate_market_slope,
    read_cached_slope,
    shrink_to_market,
    store_slope,
    MODEL_VERSION,
    STRATEGY,
    Projection,
    estimate_totals_distribution,
    predict_market,
    project,
    to_decimal,
)
from strategies.wnba_totals.model.features import build_matchup_features

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc


#: A quote older than this is not priced as though it were current.
#:
#: Tied to the recorder's own cadence rather than picked freehand. The pregame
#: recorder polls every 15 min within 6h of tip-off and every 60 min beyond it,
#: so up to an hour old is *normal operation* for a far-dated market and must
#: not be flagged. 90 minutes is that idle interval with margin, and it is
#: already the project's definition of a stale recorder (`/api/status` reports
#: unhealthy at the same bound). Anything older means a poll was genuinely
#: missed, not merely that the market is far out.
#:
#: Stale markets are still logged, as `reduced_confidence` rather than dropped:
#: dropping them would hide the staleness, and pricing them as fresh would
#: misrepresent it.
MAX_ACTIONABLE_SNAPSHOT_AGE_SECONDS = 5400.0

#: A book anchor older than this cannot mark a prediction actionable.
#:
#: Pre-registered at 60 minutes on 2026-08-05, before any measurement against
#: it. The fast leg polls sportsbook lines every 20 minutes, so 60 minutes is
#: three consecutive missed polls — an odds feed that is down, not one that is
#: merely between cycles. This is the countermeasure to the B1/B2/B10 pattern
#: (a computation that silently stops being correct when the world changes):
#: `anchored` used to mean "a book row exists", with no age check, so a dead
#: odds feed left predictions flowing against an hours-old line, marked
#: actionable.
MAX_ANCHOR_AGE_SECONDS = 3600.0


class PredictionStats:
    def __init__(self) -> None:
        self.markets_on_board = 0
        self.pregame_markets = 0
        self.quotable_markets = 0
        self.markets_seen = 0
        self.predictions_written = 0
        self.skipped_unparseable = 0
        self.skipped_insufficient = 0
        self.skipped_unknown_team = 0
        self.stale_markets = 0
        self.stale_anchors = 0
        self.suppressed_by_stale_anchor = 0
        self.actionable_predictions = 0
        self.errors = 0

    @property
    def ok(self) -> bool:
        """False when the run had work to do and did none of it.

        The failure this exists for wrote zero predictions for two and a half
        hours while reporting success on every cycle. A job that silently does
        nothing is worse than one that crashes: the crash gets noticed.

        Having no pregame markets at all is *not* a fault — during a full slate
        every game is in flight and there is genuinely nothing to price. Having
        quotable pregame markets and writing nothing is.
        """
        if self.quotable_markets == 0:
            return True
        if self.predictions_written == 0:
            return False
        # The odds-outage shape: predictions flowed, but every one that would
        # have been actionable was suppressed by a stale book anchor. That is
        # a dead feed wearing a healthy job's clothes, and the scheduler
        # should say job_degraded, not job_ok. Zero actionable with zero
        # suppressions is different — a board with no edge is a fine outcome.
        if self.actionable_predictions == 0 and self.suppressed_by_stale_anchor > 0:
            return False
        return True

    @property
    def summary(self) -> dict:
        return {
            "markets_on_board": self.markets_on_board,
            "pregame": self.pregame_markets,
            "quotable": self.quotable_markets,
            "written": self.predictions_written,
            "actionable": self.actionable_predictions,
            "stale": self.stale_markets,
            "stale_anchors": self.stale_anchors,
            "suppressed_by_stale_anchor": self.suppressed_by_stale_anchor,
            "skipped_insufficient": self.skipped_insufficient,
            "skipped_unparseable": self.skipped_unparseable,
            "skipped_unknown_team": self.skipped_unknown_team,
            "errors": self.errors,
        }


def _espn_team_id(session: Session, abbrev: str, season: int) -> str | None:
    """Resolve an ESPN abbreviation to its team id for a season."""
    from core.storage import TeamGameLog

    return session.scalar(
        select(TeamGameLog.team_id)
        .where(TeamGameLog.team_abbrev == abbrev)
        .where(TeamGameLog.season == season)
        .limit(1)
    )



def _book_consensus(
    session: Session, espn_game_id: str | None
) -> tuple[float | None, float | None, dt.datetime | None]:
    """Median sportsbook (total, home margin) — the anchors we shrink toward.

    ESPN stores `spread` as the HOME handicap (negative = home favoured), so
    the implied market margin is its negation. That sign convention is verified
    against moneyline favourites in `core.backtest.margin`, not assumed —
    getting it backwards would invert every spread pick.

    Live-odds providers are excluded: their lines are set during the game, so
    anchoring to one would drag a pregame projection toward the current score.

    The third element is the freshest `captured_at` among the rows that
    contributed a total or spread — the caller gates actionability on its age,
    because an anchor that *exists* is not the same as one that is *current*.
    """
    if not espn_game_id:
        return None, None, None
    rows = session.execute(
        select(
            SportsbookOdds.over_under,
            SportsbookOdds.spread,
            SportsbookOdds.provider_name,
            SportsbookOdds.captured_at,
        ).where(SportsbookOdds.espn_game_id == espn_game_id)
    ).all()

    def _median(values: list[float]) -> float | None:
        values.sort()
        return values[len(values) // 2] if values else None

    book = [
        (ou, sp, cap) for ou, sp, provider, cap in rows
        if "live" not in (provider or "").lower()
        and (ou is not None or sp is not None)
    ]
    totals = [float(ou) for ou, _, _ in book if ou is not None]
    spreads = [float(sp) for _, sp, _ in book if sp is not None]
    freshest = max((cap for _, _, cap in book if cap is not None), default=None)
    market_margin = _median(spreads)
    return (
        _median(totals),
        None if market_margin is None else -market_margin,
        freshest,
    )


def _anchor_staleness_note(
    anchor_age_seconds: float | None,
    *,
    anchored: bool,
    max_age_seconds: float = MAX_ANCHOR_AGE_SECONDS,
) -> str | None:
    """The confidence note when the book anchor is too old to act on.

    None means no objection: the prediction is unanchored (that case has its
    own gate) or the anchor is fresh. An anchored prediction whose anchor age
    is unknown is treated as stale — a timestamp we cannot produce is not
    evidence of freshness.
    """
    if not anchored:
        return None
    if anchor_age_seconds is not None and anchor_age_seconds < max_age_seconds:
        return None
    minutes = "?" if anchor_age_seconds is None else f"{anchor_age_seconds / 60:.0f}"
    return f"anchor stale: {minutes}m"


def _apply_anchor_guard(
    *,
    actionable: bool,
    notes: str | None,
    anchored: bool,
    anchor_age_seconds: float | None,
    stats: PredictionStats,
) -> tuple[bool, str | None, bool]:
    """Gate actionability on anchor freshness; returns (actionable, notes, stale).

    An anchor that exists but is old is the 08-04 outage shape: the odds feed
    died, the last book row froze, and `anchored` alone would keep blessing
    predictions against it. Same policy as unanchored — logged, flagged, never
    actionable, never silenced.
    """
    note = _anchor_staleness_note(anchor_age_seconds, anchored=anchored)
    if note is None:
        return actionable, notes, False

    stats.stale_anchors += 1
    if actionable:
        # Would have been actionable but for the stale anchor — the count
        # `PredictionStats.ok` uses to tell "feed is down" from "board has
        # no edge".
        stats.suppressed_by_stale_anchor += 1
    notes = f"{notes}; {note}" if notes else note
    return False, notes, True


class PredictionLogger:
    def __init__(
        self,
        sessionmaker=None,
        config: WNBATotalsConfig | None = None,
        *,
        max_snapshot_age_seconds: float = MAX_ACTIONABLE_SNAPSHOT_AGE_SECONDS,
    ) -> None:
        self._Session = sessionmaker or get_sessionmaker(get_engine())
        self.config = config or CONFIG
        self.max_snapshot_age_seconds = max_snapshot_age_seconds
        #: (as_of -> slope). The slope walks a few hundred games, so it is
        #: computed once per run, not once per market.
        self._slope_cache: dict[dt.datetime, float] = {}

    def _market_slope(self, *, session: Session, as_of: dt.datetime) -> float:
        """The winner's-curse slope, from cache where possible.

        Recomputing walks every completed game and re-derives its features —
        seconds locally, minutes against Supabase. This job runs every 20
        minutes, so it reads the daily-refreshed `model_calibration` row and
        only pays the full cost when none is fresh enough.

        Falling back to 1.0 (no shrinkage) would silently restore the bug this
        exists to fix, so the fallback is to compute it, however slow.
        """
        if as_of in self._slope_cache:
            return self._slope_cache[as_of]

        slope = read_cached_slope(session=session, as_of=as_of)
        if slope is None:
            slope = estimate_market_slope(as_of=as_of, session=session)
            store_slope(session=session, as_of=as_of, slope=slope)
            log.info("market_slope_computed", as_of=as_of.isoformat(),
                     slope=round(slope, 3))
        else:
            log.info("market_slope_cached", as_of=as_of.isoformat(),
                     slope=round(slope, 3))

        self._slope_cache[as_of] = slope
        return slope

    def run(self, as_of: dt.datetime | None = None) -> PredictionStats:
        """Predict every pregame market currently on the board.

        `as_of` is the **run's own instant**, not the newest snapshot's
        timestamp. Two reasons, and both are load-bearing:

        * `predicted_at` must be uniform across a run. The prediction log's
          unique constraint is `(market_slug, predicted_at, model_version,
          config_hash)` and every performance query groups on it, as do
          `core.shadow_run` and `/api/picks`, which both select
          `max(predicted_at)` and expect that to name one complete run. Stamping
          each row with its own snapshot's time would shatter a run into as many
          "runs" as there are distinct capture instants — and with a 200ms
          recorder that is thousands.
        * Snapshots now arrive at wildly different times, so "the newest
          snapshot" is no longer a coherent instant to compute features as of.
          The wall clock is.

        Per-market staleness does not disappear; it is recorded on each row
        (`features.snapshot_age_seconds`) so it stays auditable, and it gates
        actionability.
        """
        stats = PredictionStats()
        as_of = as_of or dt.datetime.now(UTC)

        with self._Session() as session:
            # Latest row PER MARKET, not the single newest cycle. See
            # core.board: anchoring on max(captured_at) returns only whichever
            # live game the 200ms recorder wrote last, so filtering that down to
            # pregame markets yields an empty list for the whole duration of
            # every game.
            snapshots = latest_snapshot_per_market(session, as_of=as_of)
            if not snapshots:
                log.warning("no_snapshots", hint="run the recorder first")
                return stats

            season = as_of.year

            stats.markets_on_board = len(snapshots)
            pregame = [s for s in snapshots if is_pregame(s, as_of=as_of)]
            stats.pregame_markets = len(pregame)
            markets = [
                m for m in pregame
                if m.best_bid is not None and m.best_ask is not None
            ]
            stats.quotable_markets = len(markets)

            if not markets:
                # Legitimate when every game on the board is in flight. Logged
                # at INFO with the counts that distinguish that from a fault.
                log.info(
                    "no_pregame_markets",
                    as_of=as_of.isoformat(),
                    markets_on_board=stats.markets_on_board,
                    pregame=stats.pregame_markets,
                )
                return stats

            dist = estimate_totals_distribution(as_of=as_of, session=session, season=season)
            log.info(
                "totals_distribution",
                mean=round(dist.mean, 1),
                sigma=round(dist.sigma, 1),
                season_games=dist.n_current_season,
                shrunk=dist.shrunk_toward_history,
            )

            # Home/away comes from ESPN, never from the slug: Polymarket's slug
            # order is inconsistent (18 of 285 closed markets put the HOME team
            # first), and trusting it would silently invert spread/moneyline
            # predictions. See core.team_mapping.
            dates = sorted({
                p.local_date
                for p in (parse_market_slug(m.market_slug) for m in markets)
                if p is not None
            })
            span = []
            for d in dates:
                span.extend([d, d + dt.timedelta(days=1)])
            orientation_map = orientation_from_scoreboard(
                espn_client=ESPNClient(), dates=sorted(set(span))
            )
            log.info("orientation_map_built", games=len(orientation_map))

            # One projection per event, reused across that event's ~18 markets.
            # (projection, features, was_anchored_to_a_book_line, anchor_age_s)
            projections: dict[str, tuple[Projection, object, bool, float | None]] = {}
            rows: list[Prediction] = []

            for snap in markets:
                stats.markets_seen += 1
                try:
                    row = self._predict_one(
                        session=session, snap=snap, as_of=as_of, season=season,
                        sigma=dist.sigma, projections=projections, stats=stats,
                        orientation_map=orientation_map,
                    )
                except UnknownTeamError as exc:
                    stats.skipped_unknown_team += 1
                    log.warning("unknown_team", market=snap.market_slug, error=str(exc))
                    continue
                except Exception as exc:
                    stats.errors += 1
                    log.error(
                        "prediction_failed", market=snap.market_slug,
                        error=str(exc), exc_info=True,
                    )
                    continue
                if row is not None:
                    rows.append(row)

            # ON CONFLICT DO NOTHING makes a rerun against the same snapshot
            # idempotent (same guarantee the recorder has).
            written = 0
            for row in rows:
                # Iterate MAPPER attributes, not column names: `model_config`
                # is stored under the attribute `model_config_snapshot`, so a
                # column-name loop raises AttributeError.
                values = {}
                for attr in Prediction.__mapper__.column_attrs:
                    key = attr.key
                    if key == "id":
                        continue
                    val = getattr(row, key)
                    if val is not None:
                        values[attr.columns[0].name] = val
                stmt = (
                    pg_insert(Prediction).values(**values)
                    .on_conflict_do_nothing(constraint="uq_prediction_market_time_model")
                    .returning(Prediction.id)
                )
                if session.execute(stmt).scalar() is not None:
                    written += 1
            session.commit()
            stats.predictions_written = written

        if stats.ok:
            log.info("prediction_run_complete", **stats.summary)
        else:
            # The dangerous case: there was work and none of it landed. This
            # ran undetected for 2.5 hours because it looked like success.
            log.warning(
                "prediction_run_wrote_nothing",
                hint="quotable pregame markets existed but no prediction was "
                     "written — check skipped_* and errors",
                **stats.summary,
            )
        return stats

    def _predict_one(
        self, *, session: Session, snap: MarketSnapshot, as_of: dt.datetime,
        season: int, sigma: float, projections: dict, stats: PredictionStats,
        orientation_map: dict,
    ) -> Prediction | None:
        parsed = parse_market_slug(snap.market_slug)
        if parsed is None:
            stats.skipped_unparseable += 1
            return None

        orientation = orient_for_slug(parsed, orientation_map)
        if orientation is None:
            stats.skipped_unknown_team += 1
            return None

        event_key = f"{orientation.espn_game_id}"
        if event_key not in projections:
            home_id = _espn_team_id(session, orientation.home_abbrev, season)
            away_id = _espn_team_id(session, orientation.away_abbrev, season)
            if home_id is None or away_id is None:
                stats.skipped_unknown_team += 1
                return None

            features = build_matchup_features(
                home_team_id=home_id, away_team_id=away_id,
                as_of=as_of, session=session, season=season,
                is_playoff_game=False,   # regular season; playoffs flagged by season_type
                config=self.config,
            )
            raw = project(features, config=self.config, sigma=sigma)

            # Winner's-curse correction, applied HERE so the live model is the
            # same model the backtest validated. Without it the dashboard
            # reported the raw model-minus-market gap, which measurement says
            # is ~77% our own error: a 13% displayed edge was worth about 3%.
            # The slope is computed once per run and reused across games.
            slope = self._market_slope(session=session, as_of=as_of)
            book_total, book_margin, book_captured_at = _book_consensus(
                session, orientation.espn_game_id
            )
            anchor_age = (
                (as_of - book_captured_at).total_seconds()
                if book_captured_at is not None
                else None
            )
            projections[event_key] = (
                shrink_to_market(
                    raw, market_total=book_total,
                    market_margin=book_margin, slope=slope,
                ),
                features,
                book_total is not None or book_margin is not None,
                anchor_age,
            )

        projection, features, anchored, anchor_age = projections[event_key]

        line = float(snap.line) if snap.line is not None else None
        bid = float(snap.best_bid) if snap.best_bid is not None else None
        ask = float(snap.best_ask) if snap.best_ask is not None else None

        mtype = snap.sports_market_type
        # The market is quoted from the FIRST slug team's perspective; whether
        # that team is home or away comes from ESPN, not the slug.
        quoted_side_is_home = orientation.first_is_home

        if mtype == MARKET_SPREAD:
            # "cover +L" for the quoted side means its margin > -L
            pred = predict_market(
                features=features, projection=projection,
                market_slug=snap.market_slug, sports_market_type=MARKET_SPREAD,
                line=-line if line is not None else None,
                market_bid=bid, market_ask=ask,
                config=self.config, is_home_side=quoted_side_is_home,
            )
        elif mtype == MARKET_WINNER:
            pred = predict_market(
                features=features, projection=projection,
                market_slug=snap.market_slug, sports_market_type=MARKET_WINNER,
                line=None, market_bid=bid, market_ask=ask,
                config=self.config, is_home_side=quoted_side_is_home,
            )
        elif mtype == MARKET_TOTAL:
            pred = predict_market(
                features=features, projection=projection,
                market_slug=snap.market_slug, sports_market_type=MARKET_TOTAL,
                line=line, market_bid=bid, market_ask=ask,
                config=self.config, is_over_side=True,
            )
        else:
            return None

        if pred is None:
            stats.skipped_insufficient += 1
            return None

        # No book line yet => nothing to shrink toward, so this price is the
        # RAW model opinion. Those are exactly the games that show the
        # largest edges and deserve the least trust, so they are logged but
        # never actionable. Silence would let an unshrunk 20% edge sit on the
        # board looking identical to a validated one.
        actionable = pred.is_actionable and anchored
        notes = pred.confidence_notes
        if not anchored:
            unshrunk = "no book line yet: price is unshrunk model opinion"
            notes = f"{notes}; {unshrunk}" if notes else unshrunk

        # Snapshots now arrive from writers on very different cadences, so a
        # row's quote can be minutes or hours old while the run itself is
        # current. Pricing a two-hour-old book as though it were the touch
        # would be a quiet lie, so age is recorded on every row and gates
        # actionability rather than being assumed away.
        age = snapshot_age_seconds(snap, as_of=as_of)
        stale = age > self.max_snapshot_age_seconds
        if stale:
            stats.stale_markets += 1
            note = (f"stale quote: snapshot is {age / 60:.0f} min old "
                    f"(limit {self.max_snapshot_age_seconds / 60:.0f} min)")
            notes = f"{notes}; {note}" if notes else note
            actionable = False

        actionable, notes, anchor_stale = _apply_anchor_guard(
            actionable=actionable, notes=notes, anchored=anchored,
            anchor_age_seconds=anchor_age, stats=stats,
        )

        if actionable:
            stats.actionable_predictions += 1

        features = dict(pred.features or {})
        features["snapshot_age_seconds"] = round(age, 1)
        features["snapshot_captured_at"] = snap.captured_at.isoformat()
        if anchor_age is not None:
            features["anchor_age_seconds"] = round(anchor_age, 1)

        return Prediction(
            predicted_at=as_of,
            model_version=pred.model_version,
            strategy=STRATEGY,
            market_slug=pred.market_slug,
            event_slug=snap.event_slug,
            game_id=snap.game_id,
            sports_market_type=pred.sports_market_type,
            line=snap.line,
            model_probability=to_decimal(pred.model_probability),
            model_fair_value=to_decimal(pred.model_fair_value),
            market_bid=to_decimal(pred.market_bid),
            market_ask=to_decimal(pred.market_ask),
            market_mid=to_decimal(pred.market_mid),
            edge=to_decimal(pred.edge, "0.000001"),
            features=features,
            model_config_snapshot=pred.model_config_snapshot,
            config_hash=pred.config_hash,
            is_actionable=actionable,
            reduced_confidence=(
                pred.reduced_confidence or not anchored or stale or anchor_stale
            ),
            confidence_notes=notes,
        )


def _configure_logging() -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-predictions")
    parser.add_argument("--run", action="store_true", help="predict the latest snapshot")
    args = parser.parse_args()

    _configure_logging()
    if not args.run:
        parser.error("--run is required")
    PredictionLogger().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
