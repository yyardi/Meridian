"""Pydantic models for ESPN responses.

ESPN is undocumented and will drift. Policy matches the Polymarket schemas:
require the handful of fields we genuinely depend on, allow everything else,
and normalise the two shape quirks that bite in practice.

Quirk 1 — ``score`` is sometimes ``{"value": 66.0}`` and sometimes a bare
value, depending on endpoint.
Quirk 2 — ``seasonType.id`` is a *string* ("1"/"2"/"3"), not an int.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _coerce_score(value: Any) -> int | None:
    """Handle both {"value": 66.0} and a bare 66 / "66"."""
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("value")
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


class Team(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    abbreviation: str | None = None
    display_name: str | None = Field(default=None, alias="displayName")

    @field_validator("id", mode="before")
    @classmethod
    def _stringify(cls, v: Any) -> str:
        return str(v)


class Competitor(BaseModel):
    model_config = ConfigDict(extra="allow")

    team: Team
    home_away: str | None = Field(default=None, alias="homeAway")
    score: int | None = None

    @field_validator("score", mode="before")
    @classmethod
    def _score(cls, v: Any) -> int | None:
        return _coerce_score(v)

    @property
    def is_home(self) -> bool:
        return self.home_away == "home"


class StatusType(BaseModel):
    model_config = ConfigDict(extra="allow")

    completed: bool = False


class Status(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: StatusType | None = None

    @property
    def is_completed(self) -> bool:
        return bool(self.type and self.type.completed)


class Competition(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    status: Status | None = None
    competitors: list[Competitor] = Field(default_factory=list)
    odds: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def is_completed(self) -> bool:
        return bool(self.status and self.status.is_completed)


class SeasonType(BaseModel):
    model_config = ConfigDict(extra="allow")

    # Arrives as a string; normalised to int because it is compared against
    # SEASON_TYPE_* constants all over the codebase.
    id: int | None = None
    name: str | None = None
    #: The scoreboard endpoint spells the same number `type` inside the event's
    #: `season` object (`{"year": 2026, "type": 2, "slug": "regular-season"}`),
    #: where the schedule endpoint spells it `id` inside `seasonType`. Both are
    #: live; see `Event.season_type_id`.
    type: int | None = None

    @field_validator("id", "type", mode="before")
    @classmethod
    def _to_int(cls, v: Any) -> int | None:
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None


class Event(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    date: dt.datetime | None = None
    name: str | None = None
    short_name: str | None = Field(default=None, alias="shortName")
    #: ESPN publishes the season type in TWO places and only one at a time.
    #: `seasonType` is the schedule endpoint's spelling. The scoreboard endpoint
    #: nests it instead as `season: {"year":…, "type": 2, "slug":…}` and carries
    #: no top-level `seasonType` at all. Both fields are read because both feeds
    #: are live — see `season_type_id`.
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    season: SeasonType | None = None
    competitions: list[Competition] = Field(default_factory=list)

    @field_validator("id", mode="before")
    @classmethod
    def _stringify(cls, v: Any) -> str:
        return str(v)

    @field_validator("date", mode="before")
    @classmethod
    def _parse_date(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                return None
        return v

    @property
    def competition(self) -> Competition | None:
        return self.competitions[0] if self.competitions else None

    @property
    def season_type_id(self) -> int | None:
        """The season type, from whichever field this feed happens to use.

        Returning None here is not cosmetic: `_rows_for_event` drops any event
        whose season type is unknown, which is the right guard — writing a
        preseason game into the regular-season record would corrupt every
        feature built from it. But it makes this property load-bearing, and it
        failed in the quietest possible way.

        When the scoreboard payload stopped carrying `seasonType`, this returned
        None for every game, the fetch succeeded having written 0 rows, nothing
        raised, and the scheduler's heartbeat reports `rows_written: NULL` by
        design. Eighteen days and ~51 games of results went missing behind a
        green dashboard, while the pregame model kept predicting every 20
        minutes on team form frozen at 2026-07-31.

        Reading both spellings is the fix. `tests/test_espn_season_type.py`
        pins each payload shape and asserts a completed game survives.
        """
        for source in (self.season_type, self.season):
            if source is None:
                continue
            value = source.id if source.id is not None else source.type
            if value is not None:
                return value
        return None


class ScheduleResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    events: list[Event] = Field(default_factory=list)


class ScoreboardResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    events: list[Event] = Field(default_factory=list)
