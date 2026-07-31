# Pydantic

**Role:** validate external JSON at the boundary, before it reaches the database.

## The problem it solves

ESPN's API is undocumented. Polymarket US is young and evolving. Both will change shape without warning.

Without validation, a renamed field becomes `None`, gets written as `NULL`, and surfaces months later as a model producing quiet nonsense. The bug is far from its cause and looks like a modelling problem.

Pydantic makes the failure loud and immediate, at the point of parsing.

## The validation policy

There's a real tension here, and we resolve it deliberately:

- **Too strict** → the recorder crashes at 2am on a harmless new upstream field. Data is lost permanently.
- **Too loose** → silent NULLs corrupt the dataset invisibly.

So:

```python
class Market(BaseModel):
    model_config = ConfigDict(extra="allow")   # new fields never crash us
    slug: str                                   # required — everything keys off it
    line: Decimal | None = None                 # genuinely optional
```

**Required:** the handful of fields the recorder cannot function without (`slug`).
**Optional:** everything else — moneyline has no `line`, some markets have no quotes.
**`extra="allow"`:** upstream can add fields freely.

Combined with per-market error isolation, a genuinely malformed market is logged and skipped while the other 149 are recorded. The dominant failure mode — *dying unattended* — is prevented, without accepting silent corruption.

## Decimal parsing at the boundary

Prices arrive as strings:

```json
{ "bestBidQuote": { "value": "0.9100", "currency": "USD" } }
```

They're parsed to `Decimal`, never `float`:

```python
@field_validator("value", mode="before")
@classmethod
def _parse(cls, v): return _to_decimal(v)
```

Doing this at the boundary means no `float` ever exists in the pipeline — there's no later point where precision could be lost. See [postgres.md](postgres.md).

## Type coercion

`gameId` arrives as an integer (`13002436`); the column is text. Coerce once, at the edge:

```python
@field_validator("game_id", "id", mode="before")
@classmethod
def _stringify(cls, v): return None if v is None else str(v)
```

Better here than scattered `str()` calls at call sites, where one omission is a subtle join failure.

## Convenience properties

```python
@property
def best_bid(self) -> Decimal | None:
    return self.best_bid_quote.value if self.best_bid_quote else None
```

Flattens `{"bestBidQuote": {"value": "0.91"}}` to `market.best_bid`, keeping null-handling in one place.

## We still keep the raw payload

Validation doesn't replace storing raw JSON. The `raw` JSONB column keeps the full upstream response, because:

- A parsing bug can be fixed later and re-run against stored data
- Fields we don't use today may matter tomorrow
- Re-fetching is impossible — the moment has passed

**Parse for today, store everything for tomorrow.**
