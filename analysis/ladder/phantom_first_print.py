"""First-print refinement of the phantom check, four football days, spread-only, newest gate-2 ledger rows.

Registered rule (phantom_check.py): ANY taker print through the displayed touch while the
episode stood => PHANTOM. That counts a sweep's tail (prints AT the display first, then
beyond it) as phantom, though a consumed display is what a resting order looks like.
This variant reads, per leg, the FIRST taker print after the episode opened: through the
display => the quote was not there; at or inside => it was. Both verdicts are printed.
Run inside the api image on prod, core/ and scripts/ at /app, artifacts/reads at /out:
    docker run --rm -v /opt/meridian/core:/app/core:ro -v /opt/meridian/scripts:/app/scripts:ro \
      -v /opt/meridian/artifacts/reads:/out:ro -v $PWD/analysis:/app/analysis:ro -w /app meridian-api \
      python3 analysis/ladder/phantom_first_print.py
Result 2026-10-01 is in docs/math/ladder-capture-read.md. Reads files only. Places nothing."""
import json, os, sys
sys.path.insert(0, "/app/scripts/launchers")
import phantom_check as PC

KEYS = {("2026-09-19", "cfb"), ("2026-09-20", "nfl"), ("2026-09-26", "cfb"), ("2026-09-27", "nfl")}
rows = {}
for ln in open("/out/edge_ledger.jsonl", encoding="utf-8"):
    if not ln.strip():
        continue
    r = json.loads(ln)
    k = (r.get("date"), r.get("league"))
    if r.get("gate_s") == 2.0 and k in KEYS and "opened_ts" in json.dumps(r.get("over_floor_episodes", [{}])[:1]):
        rows[k] = r

def leg_first(prints, slug, intents, disp, side):
    """(verdict, price, dt_s) for the first taker print on this leg; verdict in none/at/through."""
    ps = sorted((p for p in prints if p["slug"] == slug and p.get("taker_intent") in intents), key=lambda p: PC._epoch(p["recv"]))
    if not ps:
        return "none", None, None
    p = ps[0]; px = float(p["price"])
    thru = px > disp + 1e-9 if side == "buy" else px < disp - 1e-9
    return ("through" if thru else "at"), px, PC._epoch(p["recv"])

tot = {"registered": {}, "first": {}}
print(f"{'game':<26}{'pair':>12}{'$':>5}{'life':>6} | {'buy A':>6}{'1st lift':>10}{'+s':>6} | {'sell B':>7}{'1st hit':>9}{'+s':>6} | registered -> first-print")
eps_out = []
for k in sorted(rows):
    r = rows[k]
    for e in r["over_floor_episodes"]:
        lo, hi = e["pair"]
        if 0.0 in (float(lo), float(hi)):
            continue
        game = e["game"]
        d = PC.find_dir("/out/stream", r["dirs"], game)
        if d is None:
            print(f"{game:<26} tape not found"); continue
        t0, t1 = e["opened_ts"], e["closed_ts"]
        touch = PC.touch_at(os.path.join(d, f"slate_books_{game}.jsonl"), t0)
        if hi not in touch or lo not in touch:
            print(f"{game:<26} legs not both displayed at open"); continue
        _, A, bslug = touch[hi]
        B, _, sslug = touch[lo]
        pr = PC.prints_in(os.path.join(d, f"slate_trades_{game}.jsonl"), {bslug, sslug}, t0, t1)
        pr = [p for p in pr if PC._epoch(p["recv"]) >= t0]   # after the open only
        lifts = [p for p in pr if p["slug"] == bslug and p.get("taker_intent") in PC.LIFTS]
        hits = [p for p in pr if p["slug"] == sslug and p.get("taker_intent") in PC.HITS]
        reg = ("PHANTOM" if any(float(p["price"]) > A + 1e-9 for p in lifts) or any(float(p["price"]) < B - 1e-9 for p in hits)
               else "unproven" if not lifts and not hits else "resting")
        bv, bpx, bt = leg_first(pr, bslug, PC.LIFTS, A, "buy")
        sv, spx, st = leg_first(pr, sslug, PC.HITS, B, "sell")
        first = ("PHANTOM" if "through" in (bv, sv) else "unproven" if (bv, sv) == ("none", "none") else "resting")
        life = e.get("life_s") or 0.0
        print(f"{game:<26}{f'{hi}/{lo}':>12}{e['best_usd']:>5.0f}{life:>5.1f}s | {A:>6.3f}{(f'{bpx:.3f} {bv}' if bpx is not None else bv):>10}"
              f"{(f'{bt - t0:.1f}' if bt else ''):>6} | {B:>7.3f}{(f'{spx:.3f} {sv}' if spx is not None else sv):>9}{(f'{st - t0:.1f}' if st else ''):>6} | {reg} -> {first}")
        eps_out.append((k, game, hi, lo, e["best_usd"], life, reg, first))

def bucket(sel, name):
    for rule_i, rule in ((6, "registered"), (7, "first-print")):
        c = {}
        for x in sel:
            c.setdefault(x[rule_i], [0, 0.0]); c[x[rule_i]][0] += 1; c[x[rule_i]][1] += x[4]
        print(f"  {name:<22} {rule:<11} n={len(sel):>2} ${sum(x[4] for x in sel):>6.0f} | " + "  ".join(f"{v}: {c[v][0]} / ${c[v][1]:.0f}" for v in ("PHANTOM", "resting", "unproven") if v in c))
print()
bucket(eps_out, "all spread-only >=$25")
bucket([x for x in eps_out if x[5] >= 0.5], "lived >= 0.5 s")
bucket([x for x in eps_out if x[5] >= 1.0], "lived >= 1 s")
