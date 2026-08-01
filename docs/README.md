# Meridian docs

Short, single-topic docs. Each one should be readable in a few minutes.

The root [`README.md`](../README.md) is the project overview. These go deeper on one thing each.

## Math

The modelling, stated precisely enough to argue with.

| Doc | Question it answers |
|---|---|
| [fair-value.md](math/fair-value.md) | How do we project a game's score? |
| [ladder-curve-fit.md](math/ladder-curve-fit.md) | How do we recover the market's implied mean and σ? |
| [fees-and-spread.md](math/fees-and-spread.md) | What does a trade actually cost? |
| [clv.md](math/clv.md) | Why closing line value instead of win rate? |
| [kelly.md](math/kelly.md) | How much do we bet? |
| [pythagorean-record.md](math/pythagorean-record.md) | Does win-loss record add anything to point differential? |
| [point-in-time.md](math/point-in-time.md) | How do we make lookahead bias structurally impossible? |
| [calibration-problem.md](math/calibration-problem.md) | ⚠️ **Open problem** — why the model's probabilities carry no signal |
| [research-notes.md](math/research-notes.md) | What the betting-markets literature says, tied to actions here |
| [performance-targets.md](math/performance-targets.md) | Pre-registered bars for "good", sample sizes, gates before real money |

## Stack

One doc per tool: what it does, why it was chosen, what it replaced.

| Doc | Covers |
|---|---|
| [postgres.md](stack/postgres.md) | Database, and why NUMERIC not float |
| [sqlalchemy-alembic.md](stack/sqlalchemy-alembic.md) | ORM and migrations |
| [httpx-tenacity.md](stack/httpx-tenacity.md) | HTTP and retries |
| [pydantic.md](stack/pydantic.md) | Boundary validation |
| [structlog.md](stack/structlog.md) | Logging |
| [scientific-python.md](stack/scientific-python.md) | pandas / numpy / scipy / statsmodels |

## Infra

| Doc | Covers |
|---|---|
| [architecture.md](infra/architecture.md) | How the pieces fit together |
| [hosting.md](infra/hosting.md) | Where it runs and what it costs |
| [data-sources.md](infra/data-sources.md) | Every external API, verified |

## Reading order

New to the project? **[architecture.md](infra/architecture.md)** → **[fair-value.md](math/fair-value.md)** → **[clv.md](math/clv.md)**. That's the system, the model, and how we judge it.
