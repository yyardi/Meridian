"""The human-confirmed order path, and the invariant that replaced "no POST".

Before this feature the safety guarantee was structural: `PolymarketAuthedClient`
had no verb but GET, so **no code path could place an order**. Adding a POST
spends that guarantee. These tests are the receipt for what bought it back.

The central claim under test: **`orders_autonomous` cannot be incremented from
any non-human code path.** It is tested at every layer that could produce a
row, from the database upward, because a guarantee that holds only in the
endpoint is a guarantee that holds only until someone writes a second caller.
"""

from __future__ import annotations

import datetime as dt
import inspect
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from core import api as api_module
from core.executor import (
    ExecutionMode,
    LimitOrder,
    OrderSide,
    OutcomeSide,
    build_order,
)
from core.polymarket import client as pm_client
from core.storage import PlacedOrder, get_engine, get_sessionmaker

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 8, 4, 18, 0, tzinfo=UTC)

TEST_SLUG = "test-human-confirm-market"

_Session = get_sessionmaker(get_engine())


def _row(**over) -> PlacedOrder:
    base = dict(
        submitted_at=NOW,
        idempotency_key=f"test-{over.get('idempotency_key', 'k')}",
        mode=ExecutionMode.HUMAN_CONFIRM.value,
        market_slug=TEST_SLUG,
        side="buy",
        order_type="ORDER_TYPE_LIMIT",
        limit_price=Decimal("0.20"),
        quantity=Decimal("1"),
        accepted=False,
    )
    base.update(over)
    base["idempotency_key"] = str(base["idempotency_key"])
    return PlacedOrder(**base)


@pytest.fixture(autouse=True)
def clean_test_orders():
    """Scoped to this test's own slug — B6 wiped real rows with a broad delete."""
    yield
    with _Session() as s:
        s.execute(text("delete from orders where market_slug = :m"), {"m": TEST_SLUG})
        s.commit()


# --------------------------------------------------------------------------- #
# The invariant, at the database layer
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "mode",
    ["AUTONOMOUS", "SHADOW", "human_confirm", "HUMAN-CONFIRM", "", "hUmAn_ConFirm"],
)
def test_accepted_order_in_any_non_human_mode_is_rejected_by_postgres(mode):
    """The core claim. Not "we don't write this row" — Postgres will not store it.

    Case matters: `human_confirm` is refused. A case-insensitive comparison
    would be a hole, because `ExecutionMode` values are upper-case and anything
    else arriving here came from somewhere that is not that enum.
    """
    with _Session() as s:
        s.add(_row(mode=mode, accepted=True, idempotency_key=f"mode-{mode}"))
        with pytest.raises(IntegrityError, match="ck_orders_accepted_requires_human"):
            s.commit()
        s.rollback()


def test_human_confirm_accepted_is_the_one_allowed_combination():
    with _Session() as s:
        s.add(_row(mode="HUMAN_CONFIRM", accepted=True, idempotency_key="allowed"))
        s.commit()
        stored = s.query(PlacedOrder).filter_by(market_slug=TEST_SLUG).one()
        assert stored.accepted is True
        assert stored.mode == "HUMAN_CONFIRM"


def test_unaccepted_rows_are_allowed_in_any_mode():
    """Attempts must still be recordable. A table that only holds successes
    cannot answer "did anything ever try?", which is what an audit asks."""
    with _Session() as s:
        s.add(_row(mode="AUTONOMOUS", accepted=False, idempotency_key="auto-rejected"))
        s.commit()
        assert s.query(PlacedOrder).filter_by(mode="AUTONOMOUS").count() == 1


def test_market_orders_are_unrepresentable_in_storage_too():
    """`core.executor` cannot express a market order. Neither can the table, so
    the two cannot drift apart."""
    with _Session() as s:
        s.add(_row(order_type="ORDER_TYPE_MARKET", idempotency_key="market"))
        with pytest.raises(IntegrityError, match="ck_orders_limit_only"):
            s.commit()
        s.rollback()


def test_duplicate_idempotency_key_is_rejected():
    """A double-click, a duplicated tab, or a retry cannot become two orders."""
    with _Session() as s:
        s.add(_row(idempotency_key="dupe"))
        s.commit()
    with _Session() as s:
        s.add(_row(idempotency_key="dupe", limit_price=Decimal("0.99")))
        with pytest.raises(IntegrityError, match="idempotency_key"):
            s.commit()
        s.rollback()


def test_the_constraint_actually_exists_in_the_live_schema():
    """The counter reads 0 either because the rows are impossible or because
    nobody tried. Only the first is a guarantee, so assert the constraint."""
    with _Session() as s:
        found = s.execute(text(
            "select count(*) from pg_constraint "
            "where conname = 'ck_orders_accepted_requires_human'"
        )).scalar()
    assert found == 1, "the safety constraint is missing from the database"


# --------------------------------------------------------------------------- #
# The counters
# --------------------------------------------------------------------------- #


def test_counters_are_derived_from_rows_not_tallied():
    with _Session() as s:
        s.add(_row(mode="HUMAN_CONFIRM", accepted=True, idempotency_key="c1"))
        s.add(_row(mode="AUTONOMOUS", accepted=False, idempotency_key="c2"))
        s.commit()
        counts = api_module._order_counts(s)
    assert counts["orders_human"] == 1
    assert counts["orders_autonomous"] == 0
    assert counts["orders_rejected"] == 1


def test_autonomous_counter_reads_zero_on_a_clean_table():
    with _Session() as s:
        assert api_module._order_counts(s)["orders_autonomous"] == 0


def test_no_in_memory_order_tally_exists_in_the_api():
    """The counters must be a query, never a process-local number that resets
    on deploy and lies about history."""
    src = inspect.getsource(api_module)
    assert "real_orders_placed" not in src, "the old hardcoded 0 is still present"

    counts_src = inspect.getsource(api_module._order_counts)
    assert "session.execute" in counts_src
    assert "_ORDER_COUNTS_SQL" in counts_src
    # The SQL must actually read the orders table, not any other source.
    sql = str(api_module._ORDER_COUNTS_SQL).lower()
    assert "from orders" in sql
    assert "count(*)" in sql


def test_counters_are_not_served_from_the_status_cache():
    """The five-second cache is right for freshness signals and wrong for
    "has this system ever traded autonomously?" — a cache hit must still
    re-read the table.

    Regression guard for the mistake this nearly made: merging the counters
    into the cached dict *before* storing it, which would serve a stale count
    of real orders for five seconds after one was placed.
    """
    from fastapi.testclient import TestClient

    with TestClient(api_module.app) as c:
        c.get("/api/status")                       # populate the cache
        cached = api_module._status_cache["value"]
        assert cached is not None, "expected the status cache to be warm"
        # The cached payload must not carry the counters at all...
        assert "orders_human" not in cached
        assert "orders_autonomous" not in cached
        # ...yet the response served from that cache must.
        second = c.get("/api/status").json()
        assert "orders_human" in second
        assert "orders_autonomous" in second


def test_status_reports_both_counters():
    from fastapi.testclient import TestClient

    with TestClient(api_module.app) as c:
        body = c.get("/api/status").json()
    assert "orders_human" in body and "orders_autonomous" in body
    assert body["orders_autonomous"] == 0


# --------------------------------------------------------------------------- #
# The endpoint refuses everything except a human confirmation
# --------------------------------------------------------------------------- #


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("MERIDIAN_ORDER_TOKEN", "test-token")
    return TestClient(api_module.app)


def _body(**over) -> dict:
    base = {
        "market_slug": TEST_SLUG,
        "mode": "HUMAN_CONFIRM",
        "limit_price": 0.2,
        "quantity": 1,
    }
    base.update(over)
    return base


def test_missing_token_is_403(client):
    r = client.post("/api/orders", json=_body())
    assert r.status_code == 403


def test_wrong_token_is_403(client):
    r = client.post("/api/orders", json=_body(),
                    headers={"X-Meridian-Order-Token": "wrong"})
    assert r.status_code == 403


def test_unset_server_token_disables_ordering_entirely(monkeypatch):
    """Absent must mean closed, not open. Deploying without the variable set is
    the realistic mistake, and it has to fail safe."""
    from fastapi.testclient import TestClient

    monkeypatch.delenv("MERIDIAN_ORDER_TOKEN", raising=False)
    with TestClient(api_module.app) as c:
        r = c.post("/api/orders", json=_body(),
                   headers={"X-Meridian-Order-Token": "anything"})
    assert r.status_code == 403
    assert "not set" in r.json()["detail"]


@pytest.mark.parametrize(
    "mode", ["AUTONOMOUS", "SHADOW", "human_confirm", "", "ADMIN", "HUMAN_CONFIRM "]
)
def test_any_mode_other_than_human_confirm_is_refused(client, mode):
    """Checked before the database is touched and before the venue is called."""
    r = client.post("/api/orders", json=_body(mode=mode),
                    headers={"X-Meridian-Order-Token": "test-token"})
    assert r.status_code == 403
    assert "HUMAN_CONFIRM" in r.json()["detail"]


def test_missing_mode_is_rejected_not_defaulted(client):
    body = _body()
    del body["mode"]
    r = client.post("/api/orders", json=body,
                    headers={"X-Meridian-Order-Token": "test-token"})
    assert r.status_code == 422       # pydantic: required, no default


def test_unknown_market_is_404_not_an_invented_order(client):
    r = client.post("/api/orders", json=_body(market_slug="no-such-market-xyz"),
                    headers={"X-Meridian-Order-Token": "test-token"})
    assert r.status_code == 404


@pytest.fixture
def priced_pick():
    """A current prediction for TEST_SLUG with a real book.

    Keyed off `predictions`, not `shadow_orders`: that is the whole point of the
    change. The Kelly sizer only produces a shadow order for rows it can size
    above the venue minimum — one row in fourteen at a $35 bankroll — and a pick
    it declined to size is still a real market with a real price.
    """
    from core.storage import Prediction

    with _Session() as s:
        latest = s.scalar(text("select max(predicted_at) from predictions"))
        s.execute(text("delete from predictions where market_slug = :m"),
                  {"m": TEST_SLUG})
        s.add(Prediction(
            predicted_at=latest, market_slug=TEST_SLUG,
            model_version="test", strategy="test",
            sports_market_type="basketball_team_full_game_total",
            model_probability=Decimal("0.6000"),
            market_bid=Decimal("0.5200"), market_ask=Decimal("0.5500"),
            is_actionable=True,
        ))
        s.commit()
    yield
    with _Session() as s:
        s.execute(text("delete from predictions where market_slug = :m"),
                  {"m": TEST_SLUG})
        s.commit()


def test_a_price_far_through_the_far_touch_needs_the_hard_confirm(client, priced_pick):
    """Gate 3a, new form. The price is the human's to nudge — but 0.95 against
    an 0.55 ask is 40¢ through the far touch, which is the V14 wrong-side
    shape, and it must be unreachable without the hard confirm."""
    r = client.post("/api/orders", json=_body(limit_price=0.95, quantity=1),
                    headers={"X-Meridian-Order-Token": "test-token"})
    assert r.status_code == 422
    assert "through the far touch" in r.json()["detail"]
    # The refusal spells out both frames, so the human sees the actual trade.
    assert "price.value" in r.json()["detail"]


def test_a_nudged_price_inside_the_book_is_accepted(client, priced_pick):
    """The behaviour Part 3 exists for: the book is 0.52/0.55, the human types
    0.53 to jump the queue by a cent. Reaching the 503 (no venue credentials
    in the test env) proves every gate passed."""
    r = client.post("/api/orders", json=_body(limit_price=0.53, quantity=1),
                    headers={"X-Meridian-Order-Token": "test-token"})
    assert r.status_code not in (403, 404, 409, 422), r.json()


@pytest.mark.parametrize("price", [0.005, 0.995, 1.2, 0.0])
def test_price_outside_venue_bounds_is_refused(client, priced_pick, price):
    r = client.post("/api/orders", json=_body(limit_price=price, quantity=1),
                    headers={"X-Meridian-Order-Token": "test-token"})
    assert r.status_code == 422


def test_price_off_the_one_cent_tick_is_refused_not_rounded(client, priced_pick):
    """V2: the tick is 1¢ everywhere. 0.515 is not a placeable price, and
    silently rounding it would make the number sent differ from the number
    typed — the exact class of divergence Part 3 removes."""
    r = client.post("/api/orders", json=_body(limit_price=0.515, quantity=1),
                    headers={"X-Meridian-Order-Token": "test-token"})
    assert r.status_code == 422
    assert "tick" in r.json()["detail"]


def test_a_human_may_choose_a_size_the_model_did_not(client, priced_pick):
    """The size IS the human's to choose. This is the behaviour that was asked
    for: a row the Kelly sizer declined must still be confirmable.

    Reaching a 503 (no venue credentials in the test env) proves every gate
    passed — the request got all the way to the venue call.
    """
    r = client.post("/api/orders", json=_body(limit_price=0.52, quantity=3),
                    headers={"X-Meridian-Order-Token": "test-token"})
    assert r.status_code not in (403, 404, 409, 422), r.json()


@pytest.mark.parametrize("qty", [0, 0.001, 0.009, -1])
def test_size_below_the_venue_minimum_is_refused(client, priced_pick, qty):
    r = client.post("/api/orders", json=_body(limit_price=0.52, quantity=qty),
                    headers={"X-Meridian-Order-Token": "test-token"})
    assert r.status_code == 422
    assert "minimum" in r.json()["detail"]


def test_size_above_the_stake_cap_is_refused(client, priced_pick):
    """Fat-finger protection. There is no cancel button, so an extra zero is
    unrecoverable — 1000 contracts at 0.52 is $520 against a $35 balance."""
    r = client.post("/api/orders", json=_body(limit_price=0.52, quantity=1000),
                    headers={"X-Meridian-Order-Token": "test-token"})
    assert r.status_code == 422
    assert "cap" in r.json()["detail"]


def test_a_refused_order_writes_no_row(client, priced_pick):
    """A rejected confirmation must not reserve an idempotency key or leave a
    row behind — the next legitimate click has to still work."""
    client.post("/api/orders", json=_body(limit_price=0.52, quantity=1000),
                headers={"X-Meridian-Order-Token": "test-token"})
    client.post("/api/orders", json=_body(limit_price=0.95, quantity=1),
                headers={"X-Meridian-Order-Token": "test-token"})
    with _Session() as s:
        assert s.query(PlacedOrder).filter_by(market_slug=TEST_SLUG).count() == 0


def test_every_priced_yes_side_row_gets_order_terms_not_only_sized_ones():
    """The bug this fixes: the confirm button keyed off `shadow_orders`, which
    exist for ~7% of the board, so the rest showed "too small" — which was not
    even true. They were never too small to trade, only too small for the sizer.
    """
    from core.storage import Prediction

    # YES-side: model (0.60) is above the ask (0.55), so buying YES is the pick.
    pred = Prediction(
        market_slug="x", market_bid=Decimal("0.52"), market_ask=Decimal("0.55"),
        model_probability=Decimal("0.60"),
    )
    terms = api_module._derive_order_terms(pred)
    assert terms["supported"] is True
    assert terms["limit_price"] == 0.52          # tick-rounded bid, as the executor uses
    assert terms["min_quantity"] == 0.01


# --------------------------------------------------------------------------- #
# NO-side orders — the inversion, pinned
# --------------------------------------------------------------------------- #
#
# The rule, from docs.polymarket.us/api-reference/orders:
#
#   "The price.value field always represents the long side's price, regardless
#    of which order intent you use."
#   "To trade the NO side at any price X, set price.value = 1.00 - X."
#
# Getting this backwards does not raise, does not 400, and does not fail safe.
# It places a real position on the opposite side of a real market. These tests
# are the only thing standing between a sign error and that outcome.


def test_no_side_terms_use_the_ask_and_invert_the_cost():
    """The real 2026-08-04 TOR-GSV row: `UNDER 155.5`, bid 0.81 / ask 0.84.

    Buying NO is selling YES, so a resting NO buy joins the YES **ask** at 0.84
    and costs 1 - 0.84 = 0.16. Crossing would cost 1 - 0.81 = 0.19. Buying YES
    at the bid — the old behaviour — would have paid 0.81 for the reverse bet.
    """
    from core.storage import Prediction

    terms = api_module._derive_order_terms(Prediction(
        market_slug="x", market_bid=Decimal("0.81"), market_ask=Decimal("0.84"),
        model_probability=Decimal("0.7319"),
    ))
    assert terms["outcome"] == "NO"
    assert terms["limit_price"] == 0.84            # sent as price.value (YES side)
    assert terms["cost_per_contract"] == pytest.approx(0.16)
    assert terms["limit_price"] + terms["cost_per_contract"] == pytest.approx(1.0)


def test_yes_side_terms_are_unchanged_by_the_no_work():
    """Regression guard: the YES path must behave exactly as it did before
    outcomes existed — rest at the bid, cost equals price, no inversion."""
    from core.storage import Prediction

    terms = api_module._derive_order_terms(Prediction(
        market_slug="x", market_bid=Decimal("0.52"), market_ask=Decimal("0.55"),
        model_probability=Decimal("0.60"),
    ))
    assert terms["outcome"] == "YES"
    assert terms["limit_price"] == 0.52
    assert terms["cost_per_contract"] == 0.52      # no inversion on YES


@pytest.mark.parametrize(
    "side,outcome,expected",
    [
        (OrderSide.BUY,  OutcomeSide.YES, "ORDER_INTENT_BUY_LONG"),
        (OrderSide.SELL, OutcomeSide.YES, "ORDER_INTENT_SELL_LONG"),
        (OrderSide.BUY,  OutcomeSide.NO,  "ORDER_INTENT_BUY_SHORT"),
        (OrderSide.SELL, OutcomeSide.NO,  "ORDER_INTENT_SELL_SHORT"),
    ],
)
def test_intent_matrix_matches_the_documentation(side, outcome, expected):
    """Checked cell by cell against the venue's own table. BUY_SHORT is the one
    that matters: "Buy NO contracts (go long on No outcome)"."""
    order = LimitOrder(
        market_slug="x", side=side, limit_price=Decimal("0.84"),
        quantity=Decimal("1"), idempotency_key="k", outcome=outcome,
    )
    assert order.to_payload()["intent"] == expected


def test_no_payload_sends_the_yes_side_price_and_names_the_outcome():
    order = build_order(
        market_slug="x", side=OrderSide.BUY, limit_price=Decimal("0.84"),
        quantity=Decimal("2"), decided_at=NOW, outcome=OutcomeSide.NO,
    )
    payload = order.to_payload()
    assert payload["price"]["value"] == "0.84"          # YES-side, per the docs
    assert payload["outcomeSide"] == "OUTCOME_SIDE_NO"
    assert payload["action"] == "ORDER_ACTION_BUY"
    assert payload["intent"] == "ORDER_INTENT_BUY_SHORT"
    # ...while the human-facing cost is the inverse.
    assert order.cost_per_contract == Decimal("0.16")
    assert order.stake == Decimal("0.32")               # 0.16 x 2


def test_cost_and_stake_are_not_the_price_on_a_no_order():
    """The specific confusion this guards: a $25 cap charged against `price`
    instead of `cost` sizes a cheap NO ~5x too small and an expensive one
    ~5x too big."""
    no = build_order(market_slug="x", side=OrderSide.BUY,
                     limit_price=Decimal("0.84"), quantity=Decimal("10"),
                     decided_at=NOW, outcome=OutcomeSide.NO)
    yes = build_order(market_slug="x", side=OrderSide.BUY,
                      limit_price=Decimal("0.84"), quantity=Decimal("10"),
                      decided_at=NOW, outcome=OutcomeSide.YES)
    assert no.stake == Decimal("1.60")
    assert yes.stake == Decimal("8.40")
    assert no.stake != yes.stake


def test_yes_and_no_orders_do_not_share_an_idempotency_key():
    """Same market, same price, opposite positions. A shared key would make the
    second one silently vanish as a duplicate."""
    common = dict(market_slug="x", side=OrderSide.BUY,
                  limit_price=Decimal("0.84"), quantity=Decimal("1"), decided_at=NOW)
    assert (build_order(**common, outcome=OutcomeSide.YES).idempotency_key
            != build_order(**common, outcome=OutcomeSide.NO).idempotency_key)


def test_existing_yes_keys_are_byte_identical_to_before_outcomes_existed():
    """1,700 rows in `shadow_orders` carry keys generated without an outcome.
    Changing the YES key would break `on_conflict_do_nothing` and re-insert the
    lot, so the YES form must be unchanged."""
    from core.executor import make_idempotency_key

    legacy = "mer-" + __import__("hashlib").sha256(
        f"x|{NOW.isoformat()}|0.84".encode()
    ).hexdigest()[:32]
    assert make_idempotency_key(
        market_slug="x", decided_at=NOW, limit_price=Decimal("0.84")
    ) == legacy


def test_venue_price_bounds_are_enforced_locally():
    """price.value must be 0.01-0.99. A NO derived from a 1.00 ask has to fail
    here, not at the venue."""
    with pytest.raises(ValueError, match="outside the venue"):
        build_order(market_slug="x", side=OrderSide.BUY, limit_price=Decimal("1.00"),
                    quantity=Decimal("1"), decided_at=NOW, outcome=OutcomeSide.NO)


def test_a_no_side_row_can_be_confirmed_end_to_end(client):
    """The behaviour that was asked for: UNDER rows are orderable.

    Reaching past every gate (403/404/409/422) means the request got all the way
    to the venue call with the NO payload built.
    """
    from core.storage import Prediction

    slug = TEST_SLUG + "-noside"
    with _Session() as s:
        latest = s.scalar(text("select max(predicted_at) from predictions"))
        s.add(Prediction(
            predicted_at=latest, market_slug=slug, model_version="t", strategy="t",
            sports_market_type="basketball_team_full_game_total",
            model_probability=Decimal("0.7319"),
            market_bid=Decimal("0.8100"), market_ask=Decimal("0.8400"),
            is_actionable=True,
        ))
        s.commit()
    try:
        # The request price is in the NO cost frame the ticket displays:
        # resting NO cost = 1 - 0.84 ask = 0.16. The server converts to the
        # YES-frame price.value (0.84) itself.
        r = client.post("/api/orders",
                        json=_body(market_slug=slug, limit_price=0.16, quantity=1),
                        headers={"X-Meridian-Order-Token": "test-token"})
        assert r.status_code not in (403, 404, 409, 422), r.json()
    finally:
        with _Session() as s:
            s.execute(text("delete from orders where market_slug = :m"), {"m": slug})
            s.execute(text("delete from predictions where market_slug = :m"), {"m": slug})
            s.commit()


def _seed_pick(slug: str, *, bid: str, ask: str, model: str):
    """A prediction plus the snapshot that gives it a future tip-off.

    `/api/picks` filters to pregame rows by joining `market_snapshots` for
    `game_start_time`. Without the snapshot the row is dropped and any test
    against it skips — which is a test that proves nothing.
    """
    from core.storage import MarketSnapshot, Prediction

    start = dt.datetime.now(UTC) + dt.timedelta(hours=3)
    with _Session() as s:
        latest = s.scalar(text("select max(predicted_at) from predictions"))
        s.execute(text("delete from predictions where market_slug = :m"), {"m": slug})
        s.execute(text("delete from market_snapshots where market_slug = :m"), {"m": slug})
        s.add(Prediction(
            predicted_at=latest, market_slug=slug, model_version="t", strategy="t",
            sports_market_type="basketball_team_full_game_total",
            model_probability=Decimal(model),
            market_bid=Decimal(bid), market_ask=Decimal(ask),
            is_actionable=True,
        ))
        s.add(MarketSnapshot(
            captured_at=dt.datetime.now(UTC), market_slug=slug, is_live=False,
            game_start_time=start,
        ))
        s.commit()


def _unseed_pick(slug: str):
    with _Session() as s:
        s.execute(text("delete from predictions where market_slug = :m"), {"m": slug})
        s.execute(text("delete from market_snapshots where market_slug = :m"), {"m": slug})
        s.execute(text("delete from orders where market_slug = :m"), {"m": slug})
        s.commit()


def test_no_row_reports_the_book_in_the_no_frame():
    """A row must quote one book from one side.

    The bug: `UNDER 155.5` printed `BUY AT 0.20` alongside `bid 0.80 / ask 0.83`.
    Every number was individually correct and the row was incoherent — the
    ticket columns were inverted to UNDER while the book columns still quoted
    OVER. The venue shows that market as bid 0.17 / ask 0.20.

    A binary's sides are one book from opposite ends:
    `NO bid = 1 - YES ask`, `NO ask = 1 - YES bid`.
    """
    from fastapi.testclient import TestClient

    slug = TEST_SLUG + "-frame"
    _seed_pick(slug, bid="0.8000", ask="0.8300", model="0.7319")   # OVER prob
    try:
        with TestClient(api_module.app) as c:
            rows = c.get("/api/picks").json()["picks"]
        row = next((r for r in rows if r["market_slug"] == slug), None)
        assert row is not None, "seeded pick did not reach /api/picks"

        assert row["side"] == "UNDER"
        # Shown in the position's own frame — matches the venue's screen.
        assert row["bid"] == pytest.approx(0.17)
        assert row["ask"] == pytest.approx(0.20)
        assert row["model"] == pytest.approx(0.2681)      # P(UNDER), not P(OVER)
        # Raw YES-side book preserved, because every stored price lives there.
        assert row["yes_frame"] == {"bid": 0.80, "ask": 0.83, "model": 0.7319}
        # Spread is frame-invariant.
        assert row["spread"] == pytest.approx(0.03)
        # BUY AT is the RESTING price — the number the order sends — and the
        # crossing cost is its own column. Before Part 3 the ticket showed
        # 0.20 (the ask) while the order posted at 0.17, and return_pct was
        # computed off the display number.
        assert row["ticket"]["buy_at"] == pytest.approx(0.17)
        assert row["ticket"]["cross_at"] == pytest.approx(0.20)
        assert row["order"]["cost_per_contract"] == pytest.approx(0.17)
        # Ticket-displayed price == what would be stored, frame-converted.
        assert row["ticket"]["buy_at"] == pytest.approx(
            1.0 - row["order"]["limit_price"])
    finally:
        _unseed_pick(slug)


def test_yes_row_book_is_untouched_by_the_frame_flip():
    """Regression guard: OVER rows already quoted the right side and must not
    move. YES frame and display frame are the same thing there."""
    from fastapi.testclient import TestClient

    slug = TEST_SLUG + "-yesframe"
    _seed_pick(slug, bid="0.5200", ask="0.5500", model="0.6000")
    try:
        with TestClient(api_module.app) as c:
            rows = c.get("/api/picks").json()["picks"]
        row = next((r for r in rows if r["market_slug"] == slug), None)
        assert row is not None, "seeded pick did not reach /api/picks"
        assert row["side"] == "OVER"
        assert (row["bid"], row["ask"], row["model"]) == (0.52, 0.55, 0.6)
        assert row["yes_frame"] == {"bid": 0.52, "ask": 0.55, "model": 0.6}
    finally:
        _unseed_pick(slug)


def test_a_no_row_does_not_inherit_a_yes_side_size():
    """`shadow_run.py` sizes every pick as a YES buy — `probability=model`,
    `price=market_ask`, both YES-frame, with no concept of a NO position.

    So a stored size on a NO row is Kelly's answer to "how much YES should I
    buy", not "how much NO". `SELL TOR +11.5` displayed `SIZE 1.1` from a YES
    buy priced off an 18-hour-old 0.42 bid while the live pick was NO at 0.50 —
    wrong side, wrong price, wrong time — and that number was prefilled as the
    confirm box default.
    """
    from fastapi.testclient import TestClient
    from core.storage import ShadowOrder

    slug = TEST_SLUG + "-noshadow"
    _seed_pick(slug, bid="0.8000", ask="0.8300", model="0.7319")   # a NO pick
    with _Session() as s:
        s.execute(text("delete from shadow_orders where market_slug = :m"), {"m": slug})
        s.add(ShadowOrder(
            decided_at=NOW, idempotency_key="test-wrongside", market_slug=slug,
            sports_market_type="basketball_team_full_game_total",
            side="buy", limit_price=Decimal("0.4200"), quantity=Decimal("1.0889"),
            would_rest=True, mode="SHADOW",
        ))
        s.commit()
    try:
        with TestClient(api_module.app) as c:
            rows = c.get("/api/picks").json()["picks"]
        row = next((r for r in rows if r["market_slug"] == slug), None)
        assert row is not None, "seeded pick did not reach /api/picks"
        assert row["side"] == "UNDER"
        # A shadow order exists, but it is YES-side and must not be inherited.
        assert row["shadow"] is not None
        assert row["order"]["sized_by_model"] is False
        assert row["order"]["default_quantity"] == 0.01     # venue minimum
        assert row["ticket"]["too_small"] is True           # SIZE reads "not sized"
    finally:
        with _Session() as s:
            s.execute(text("delete from shadow_orders where market_slug = :m"), {"m": slug})
            s.commit()
        _unseed_pick(slug)


def test_a_yes_row_still_inherits_its_model_size():
    """The counterpart: on a YES row the stored size *is* the right question's
    answer, so it must still prefill."""
    from fastapi.testclient import TestClient
    from core.storage import ShadowOrder

    slug = TEST_SLUG + "-yesshadow"
    _seed_pick(slug, bid="0.5200", ask="0.5500", model="0.6000")   # a YES pick
    with _Session() as s:
        s.execute(text("delete from shadow_orders where market_slug = :m"), {"m": slug})
        s.add(ShadowOrder(
            decided_at=NOW, idempotency_key="test-rightside", market_slug=slug,
            sports_market_type="basketball_team_full_game_total",
            side="buy", limit_price=Decimal("0.5200"), quantity=Decimal("3.0000"),
            would_rest=True, mode="SHADOW",
        ))
        s.commit()
    try:
        with TestClient(api_module.app) as c:
            rows = c.get("/api/picks").json()["picks"]
        row = next((r for r in rows if r["market_slug"] == slug), None)
        assert row is not None
        assert row["side"] == "OVER"
        assert row["order"]["sized_by_model"] is True
        assert row["order"]["default_quantity"] == 3.0
    finally:
        with _Session() as s:
            s.execute(text("delete from shadow_orders where market_slug = :m"), {"m": slug})
            s.commit()
        _unseed_pick(slug)


def test_the_client_cannot_choose_the_outcome(client):
    """`outcome` is not a request field — the server determines direction from
    the model and the book. A caller must not be able to flip a pick to its
    opposite side by asking."""
    r = client.post("/api/orders",
                    json=_body(outcome="NO"),
                    headers={"X-Meridian-Order-Token": "test-token"})
    assert r.status_code == 422       # extra="forbid"


def test_no_order_terms_without_a_usable_book():
    """The one case that legitimately gets no button."""
    from core.storage import Prediction

    assert api_module._derive_order_terms(
        Prediction(market_slug="x", market_bid=None, market_ask=None)
    ) is None


def test_extra_fields_are_forbidden(client):
    """`extra="forbid"` — a request smuggling `order_type: market` must fail
    loudly rather than have the field silently ignored."""
    r = client.post("/api/orders", json=_body(order_type="ORDER_TYPE_MARKET"),
                    headers={"X-Meridian-Order-Token": "test-token"})
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# Read-only client stays read-only
# --------------------------------------------------------------------------- #


def test_read_only_client_still_has_no_mutating_verb():
    """The whole reason order submission went in a separate class."""
    public = {n for n in dir(pm_client.PolymarketAuthedClient) if not n.startswith("_")}
    assert public == {"get", "close"}
    src = inspect.getsource(pm_client.PolymarketAuthedClient)
    for verb in ("_client.post", "_client.put", "_client.patch", "_client.delete"):
        assert verb not in src


def test_order_client_can_submit_and_cancel_never_modify():
    """Updated on purpose 2026-08-07: `cancel_order` was added for the human
    cancel button (V21) — a deliberate widening, decided here. Amending an
    order remains inexpressible, and DELETE exists only inside cancel_order.
    The full cancel-path invariants live in tests/test_cancel_path.py."""
    public = {n for n in dir(pm_client.PolymarketOrderClient) if not n.startswith("_")}
    assert public == {"submit_limit_order", "cancel_order", "close"}
    src = inspect.getsource(pm_client.PolymarketOrderClient)
    for verb in ("_client.put", "_client.patch"):
        assert verb not in src


def test_order_client_sends_the_body_it_signed():
    """Trap #2 again: `content=` sends the exact string; `json=` would
    re-serialise and sign different bytes than it sends."""
    src = inspect.getsource(pm_client.PolymarketOrderClient._post_signed)
    assert "content=body" in src
    assert "json=" not in src


# --------------------------------------------------------------------------- #
# Limit-only, all the way down
# --------------------------------------------------------------------------- #


def test_venue_payload_is_always_a_limit_order():
    order = build_order(
        market_slug=TEST_SLUG, side=OrderSide.BUY, limit_price=Decimal("0.20"),
        quantity=Decimal("5"), decided_at=NOW,
    )
    payload = order.to_payload()
    assert payload["type"] == "ORDER_TYPE_LIMIT"
    assert payload["participateDontInitiate"] is True      # post-only by default
    assert payload["manualOrderIndicator"] == "MANUAL_ORDER_INDICATOR_MANUAL"


def test_order_type_cannot_be_set_by_a_caller():
    """`order_type` is `init=False`, so there is no argument to pass."""
    with pytest.raises(TypeError):
        LimitOrder(
            market_slug="x", side=OrderSide.BUY, limit_price=Decimal("0.2"),
            quantity=Decimal("1"), idempotency_key="k",
            order_type="ORDER_TYPE_MARKET",     # type: ignore[call-arg]
        )


def test_post_only_is_the_default_so_a_crossing_limit_is_refused_not_filled():
    order = build_order(
        market_slug=TEST_SLUG, side=OrderSide.BUY, limit_price=Decimal("0.20"),
        quantity=Decimal("5"), decided_at=NOW,
    )
    assert order.to_payload()["participateDontInitiate"] is True
    assert order.to_payload(post_only=False)["participateDontInitiate"] is False


# --------------------------------------------------------------------------- #
# Nothing else in the codebase can reach the venue
# --------------------------------------------------------------------------- #


def test_only_the_api_endpoint_imports_the_order_client():
    """A second caller is how "only a human can order" quietly stops being true.

    If this fails, a new module gained the ability to place orders. That may be
    correct — but it must be a decision someone made on purpose, and this test
    is where they have to say so.
    """
    import pathlib

    root = pathlib.Path(__file__).parent.parent
    # core/fill_watcher.py added 2026-08-05, on purpose: it submits the
    # pre-authorized exits — orders whose every term a human fixed on the
    # ticket, which the watcher may only transmit when the entry fills.
    allowed = {"core/api.py", "core/polymarket/client.py", "core/fill_watcher.py"}
    offenders = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if rel.startswith((".venv", "tests/")) or rel in allowed:
            continue
        if "PolymarketOrderClient" in path.read_text():
            offenders.append(rel)
    assert not offenders, f"these modules can now place orders: {offenders}"


def test_executor_execute_still_refuses_to_place_anything():
    """`Executor.execute` is the autonomous path. It must remain incapable of
    placing an order regardless of what the human path can do."""
    from core.executor import Executor, ExecutorConfig

    src = inspect.getsource(Executor.execute)
    assert "PolymarketOrderClient" not in src
    assert "submit" not in src
    cfg = ExecutorConfig()
    assert cfg.mode is ExecutionMode.SHADOW
    assert cfg.kill_switch is True
